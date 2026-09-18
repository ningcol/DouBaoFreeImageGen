const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const source = fs.readFileSync(path.join(__dirname, "background.js"), "utf8");

const sentToTabs = [];
const wsMessages = [];
let runtimeMessageListener = null;

const chrome = {
  storage: {
    sync: {
      get(_keys, callback) {
        callback({ wsUrl: "ws://test" });
      },
    },
  },
  cookies: {
    async getAll() {
      return [];
    },
    async remove() {},
  },
  webNavigation: {
    onCommitted: { addListener() {} },
  },
  runtime: {
    lastError: null,
    onInstalled: { addListener() {} },
    onMessage: {
      addListener(listener) {
        runtimeMessageListener = listener;
      },
    },
  },
  debugger: {
    onEvent: { addListener() {} },
    attach(_target, _version, callback) {
      callback();
    },
    sendCommand(_target, _method, _params, callback) {
      if (callback) callback();
    },
    detach() {},
  },
  tabs: {
    onUpdated: { addListener() {} },
    onRemoved: { addListener() {} },
    sendMessage(tabId, message, callback) {
      sentToTabs.push({ tabId, message });
      chrome.runtime.lastError = null;
      if (callback) callback();
    },
  },
};

class FakeWebSocket {
  static OPEN = 1;
  static CONNECTING = 0;

  constructor() {
    this.readyState = FakeWebSocket.OPEN;
  }

  send(message) {
    wsMessages.push(JSON.parse(message));
  }

  close() {
    this.readyState = 3;
  }
}

const context = vm.createContext({
  chrome,
  WebSocket: FakeWebSocket,
  console,
  setTimeout,
  clearTimeout,
  atob: (value) => Buffer.from(value, "base64").toString("utf8"),
  testWs: {
    readyState: FakeWebSocket.OPEN,
    send(message) {
      wsMessages.push(JSON.parse(message));
    },
  },
});

vm.runInContext(source, context, { filename: "background.js" });
vm.runInContext(
  "ws = testWs; doubaoTabIds.add(101); doubaoTabIds.add(102);",
  context
);

function dispatch(requestId, prompt) {
  vm.runInContext(
    `dispatchTaskToTab(${JSON.stringify(
      JSON.stringify({ type: "draw", request_id: requestId, prompt })
    )})`,
    context
  );
}

dispatch("req-1", "prompt-one");
dispatch("req-2", "prompt-two");

assert.deepStrictEqual(
  sentToTabs.slice(0, 2).map((item) => item.tabId),
  [101, 102],
  "two ready tabs should each receive one task"
);
assert.strictEqual(sentToTabs[0].message.requestId, "req-1");
assert.strictEqual(sentToTabs[1].message.requestId, "req-2");

dispatch("req-3", "prompt-three");
assert.strictEqual(sentToTabs.length, 2, "busy tabs must not receive another task");
assert.ok(
  wsMessages.some(
    (item) =>
      item.type === "error" &&
      item.request_id === "req-3" &&
      item.message === "No available Doubao tab"
  ),
  "server should receive a capacity error when no tab is available"
);

assert.ok(runtimeMessageListener, "background should register a runtime message listener");
runtimeMessageListener(
  {
    type: "COLLECTED_IMAGE_URLS",
    requestId: "req-1",
    urls: ["https://example/image-1.png"],
  },
  { tab: { id: 101 } }
);

assert.ok(
  wsMessages.some(
    (item) =>
      item.type === "collectedImageUrls" &&
      item.request_id === "req-1" &&
      item.urls[0] === "https://example/image-1.png"
  ),
  "result should preserve request_id when sent back to the server"
);

dispatch("req-4", "prompt-four");
assert.strictEqual(
  sentToTabs[sentToTabs.length - 1].tabId,
  101,
  "a tab should become schedulable again after its result is returned"
);

const legacy = vm.runInContext("parseServerTask('legacy prompt')", context);
assert.strictEqual(legacy.requestId, null);
assert.strictEqual(legacy.prompt, "legacy prompt");

const state = vm.runInContext(
  "({ready: doubaoTabIds.size, busy: busyTabs.size})",
  context
);
assert.strictEqual(state.ready, 2);
assert.strictEqual(state.busy, 2);

console.log("background dispatch tests passed");
