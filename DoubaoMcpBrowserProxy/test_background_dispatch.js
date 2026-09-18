const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const source = fs.readFileSync(path.join(__dirname, "background.js"), "utf8");

const sentToTabs = [];
const wsMessages = [];
let runtimeMessageListener = null;
let tabUpdatedListener = null;
let tabRemovedListener = null;
let debuggerEventListener = null;

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
    onEvent: {
      addListener(listener) {
        debuggerEventListener = listener;
      },
    },
    attach(_target, _version, callback) {
      callback();
    },
    sendCommand(_target, method, _params, callback) {
      if (method === "Network.getResponseBody") {
        return Promise.resolve({
          body: 'data: {"event_data":"{\\\"message\\\":{\\\"content\\\":\\\"{\\\\\\\"data\\\\\\\":[{\\\\\\\"image_raw\\\\\\\":{\\\\\\\"url\\\\\\\":\\\\\\\"https://example/stale.png\\\\\\\"}}]}\\\"}}"}\n',
          base64Encoded: false,
        });
      }
      if (callback) callback();
      return Promise.resolve({});
    },
    detach() {},
  },
  tabs: {
    query(_query, callback) {
      callback([]);
    },
    onUpdated: {
      addListener(listener) {
        tabUpdatedListener = listener;
      },
    },
    onRemoved: {
      addListener(listener) {
        tabRemovedListener = listener;
      },
    },
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

assert.ok(tabUpdatedListener, "background should register tab update listener");
assert.ok(tabRemovedListener, "background should register tab removal listener");
assert.ok(debuggerEventListener, "background should register debugger event listener");

// A tab that navigates away must stop advertising capacity and fail only its
// currently assigned request.
const messagesBeforeNavigate = wsMessages.length;
tabUpdatedListener(
  102,
  { url: "https://example.com/", status: "loading" },
  { id: 102, url: "https://example.com/" }
);
const afterNavigate = vm.runInContext(
  "({known: doubaoTabIds.has(102), busy: busyTabs.has(102)})",
  context
);
assert.strictEqual(afterNavigate.known, false);
assert.strictEqual(afterNavigate.busy, false);
assert.ok(
  wsMessages.slice(messagesBeforeNavigate).some(
    (item) =>
      item.type === "error" &&
      item.request_id === "req-2" &&
      item.message.includes("navigated away")
  ),
  "navigating away should fail that tab's active request"
);

// Freeze the MCP request that owns a network stream. If the tab is reused
// before the old stream finishes, the late result must be ignored.
vm.runInContext("doubaoTabIds.add(101); busyTabs.set(101, 'old-request');", context);
debuggerEventListener(
  { tabId: 101 },
  "Network.responseReceived",
  {
    requestId: "network-old",
    response: { headers: { "content-type": "text/event-stream" } },
  }
);
vm.runInContext("busyTabs.set(101, 'new-request');", context);
const tabMessagesBeforeStaleStream = sentToTabs.length;

Promise.resolve(
  debuggerEventListener(
    { tabId: 101 },
    "Network.loadingFinished",
    { requestId: "network-old" }
  )
).then(() => {
  assert.strictEqual(
    sentToTabs.length,
    tabMessagesBeforeStaleStream,
    "late EventStream output must not be delivered to a newer task"
  );
  console.log("background dispatch tests passed");
});
