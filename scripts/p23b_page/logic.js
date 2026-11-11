(function (root) {
  "use strict";

  var LABELS = ["ja", "en", "both", "unclear"];
  var ORDERS = ["ja_en", "en_ja"];

  function createState(items) {
    return { items: items.map(function (i) { return { id: i.id, clip: i.clip }; }), answers: {}, index: 0 };
  }

  function current(state) {
    return state.items[state.index];
  }

  function entry(state, id) {
    if (!state.answers[id]) state.answers[id] = { label: null, order: null, note: "", ts: null, answeredAt: null };
    return state.answers[id];
  }

  function answer(state, label, nowIso) {
    if (LABELS.indexOf(label) < 0) throw new Error("unknown label: " + label);
    var e = entry(state, current(state).id);
    e.label = label;
    if (label !== "both") e.order = null;
    e.ts = nowIso;
    return e;
  }

  function setOrder(state, order) {
    if (ORDERS.indexOf(order) < 0) throw new Error("unknown order: " + order);
    var e = entry(state, current(state).id);
    if (e.label !== "both") return null;
    e.order = order;
    return e;
  }

  function setNote(state, text) {
    var e = entry(state, current(state).id);
    e.note = String(text);
    return e;
  }

  function goto_(state, i) {
    state.index = Math.max(0, Math.min(state.items.length, i));
    return state.index;
  }

  function isDone(state) {
    return state.index >= state.items.length;
  }

  function answeredCount(state) {
    return state.items.filter(function (i) {
      return state.answers[i.id] && state.answers[i.id].label;
    }).length;
  }

  function firstUnanswered(state) {
    for (var k = 0; k < state.items.length; k++) {
      var a = state.answers[state.items[k].id];
      if (!a || !a.label) return k;
    }
    return state.items.length;
  }

  function exportLabels(state, nowIso) {
    var labels = [];
    state.items.forEach(function (item, k) {
      var a = state.answers[item.id];
      if (!a || !a.label) return;
      labels.push({
        id: item.id,
        label: a.label,
        order: a.label === "both" ? a.order : null,
        note: a.note || "",
        position: k + 1,
        timestamp: a.ts,
      });
    });
    return {
      tool: "p23b-label",
      version: 1,
      exported_at: nowIso,
      total: state.items.length,
      answered: labels.length,
      labels: labels,
    };
  }

  function serialize(state) {
    return JSON.stringify({ index: state.index, answers: state.answers });
  }

  function restore(state, raw) {
    if (!raw) return state;
    var data;
    try { data = JSON.parse(raw); } catch (e) { return state; }
    if (!data || typeof data !== "object" || !data.answers || typeof data.answers !== "object") return state;
    state.items.forEach(function (item) {
      var a = data.answers[item.id];
      if (!a || typeof a !== "object") return;
      var label = LABELS.indexOf(a.label) >= 0 ? a.label : null;
      state.answers[item.id] = {
        label: label,
        order: label === "both" && ORDERS.indexOf(a.order) >= 0 ? a.order : null,
        note: typeof a.note === "string" ? a.note : "",
        ts: typeof a.ts === "string" ? a.ts : null,
      };
    });
    if (typeof data.index === "number") goto_(state, data.index | 0);
    return state;
  }

  var api = {
    LABELS: LABELS, ORDERS: ORDERS, createState: createState, current: current, answer: answer,
    setOrder: setOrder, setNote: setNote, goto: goto_, isDone: isDone, answeredCount: answeredCount,
    firstUnanswered: firstUnanswered, exportLabels: exportLabels, serialize: serialize, restore: restore,
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.P23bLogic = api;
})(typeof window !== "undefined" ? window : globalThis);
