var __dsPreview = (() => {
  var __create = Object.create;
  var __defProp = Object.defineProperty;
  var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
  var __getOwnPropNames = Object.getOwnPropertyNames;
  var __getProtoOf = Object.getPrototypeOf;
  var __hasOwnProp = Object.prototype.hasOwnProperty;
  var __esm = (fn, res, err) => function __init() {
    if (err) throw err[0];
    try {
      return fn && (res = (0, fn[__getOwnPropNames(fn)[0]])(fn = 0)), res;
    } catch (e) {
      throw err = [e], e;
    }
  };
  var __commonJS = (cb, mod) => function __require() {
    try {
      return mod || (0, cb[__getOwnPropNames(cb)[0]])((mod = { exports: {} }).exports, mod), mod.exports;
    } catch (e) {
      throw mod = 0, e;
    }
  };
  var __export = (target, all) => {
    for (var name in all)
      __defProp(target, name, { get: all[name], enumerable: true });
  };
  var __copyProps = (to, from, except, desc) => {
    if (from && typeof from === "object" || typeof from === "function") {
      for (let key of __getOwnPropNames(from))
        if (!__hasOwnProp.call(to, key) && key !== except)
          __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
    }
    return to;
  };
  var __reExport = (target, mod, secondTarget) => (__copyProps(target, mod, "default"), secondTarget && __copyProps(secondTarget, mod, "default"));
  var __toESM = (mod, isNodeMode, target) => (target = mod != null ? __create(__getProtoOf(mod)) : {}, __copyProps(
    // If the importer is in node compatibility mode or this is not an ESM
    // file that has been converted to a CommonJS file using a Babel-
    // compatible transform (i.e. "__esModule" has not been set), then set
    // "default" to the CommonJS "module.exports" for node compatibility.
    isNodeMode || !mod || !mod.__esModule ? __defProp(target, "default", { value: mod, enumerable: true }) : target,
    mod
  ));
  var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

  // <define:import.meta.env>
  var init_define_import_meta_env = __esm({
    "<define:import.meta.env>"() {
    }
  });

  // ds-raw:__ds_raw__
  var require_ds_raw = __commonJS({
    "ds-raw:__ds_raw__"(exports, module) {
      init_define_import_meta_env();
      module.exports = window.SmarterVoteDS;
    }
  });

  // shim:react-shim
  var require_react_shim = __commonJS({
    "shim:react-shim"(exports, module) {
      init_define_import_meta_env();
      var R = window.React;
      function np(p, k) {
        var o = {};
        for (var x in p) if (x !== "children") o[x] = p[x];
        if (k !== void 0) o.key = k;
        return o;
      }
      function jsx2(t, p, k) {
        var c = p && p.children;
        return c === void 0 ? R.createElement(t, np(p, k)) : R.createElement(t, np(p, k), c);
      }
      function jsxs2(t, p, k) {
        return R.createElement.apply(R, [t, np(p, k)].concat(p.children));
      }
      module.exports = R;
      module.exports.jsx = jsx2;
      module.exports.jsxs = jsxs2;
      module.exports.jsxDEV = function(t, p, k, s) {
        return (s ? jsxs2 : jsx2)(t, p, k);
      };
      module.exports.Fragment = R.Fragment;
    }
  });

  // .design-sync/previews/Button.tsx
  var Button_exports = {};
  __export(Button_exports, {
    CallToActionExample: () => CallToActionExample,
    DisabledState: () => DisabledState,
    PillFilterRow: () => PillFilterRow,
    Sizes: () => Sizes,
    VariantSweep: () => VariantSweep
  });
  init_define_import_meta_env();

  // ds-shim:ds
  var ds_exports = {};
  __export(ds_exports, {
    default: () => ds_default
  });
  init_define_import_meta_env();
  __reExport(ds_exports, __toESM(require_ds_raw()));
  var g = window.SmarterVoteDS;
  var ds_default = "default" in g ? g.default : g;

  // .design-sync/previews/Button.tsx
  var import_jsx_runtime = __toESM(require_react_shim());
  function VariantSweep() {
    return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { style: { display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }, children: [
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ds_exports.Button, { variant: "primary", children: "View Race" }),
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ds_exports.Button, { variant: "secondary", children: "Cancel" }),
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ds_exports.Button, { variant: "outline", children: "Compare Candidates" }),
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ds_exports.Button, { variant: "pill", children: "All Issues" }),
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ds_exports.Button, { variant: "danger", children: "Retire Race" })
    ] });
  }
  function Sizes() {
    return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { style: { display: "flex", gap: 10, alignItems: "center" }, children: [
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ds_exports.Button, { variant: "primary", size: "sm", children: "Explore" }),
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ds_exports.Button, { variant: "primary", size: "md", children: "Explore" }),
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ds_exports.Button, { variant: "primary", size: "lg", children: "Explore" })
    ] });
  }
  function PillFilterRow() {
    return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { style: { display: "flex", gap: 8, flexWrap: "wrap" }, children: [
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ds_exports.Button, { variant: "pill", active: true, children: "All Races" }),
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ds_exports.Button, { variant: "pill", children: "Senate" }),
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ds_exports.Button, { variant: "pill", children: "Governor" }),
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ds_exports.Button, { variant: "pill", children: "House" }),
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ds_exports.Button, { variant: "pill", children: "Ballot Measures" })
    ] });
  }
  function DisabledState() {
    return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { style: { display: "flex", gap: 10, alignItems: "center" }, children: [
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ds_exports.Button, { variant: "primary", disabled: true, children: "Publish Race" }),
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ds_exports.Button, { variant: "outline", disabled: true, children: "Regenerate Forecast" })
    ] });
  }
  function CallToActionExample() {
    return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { style: { display: "flex", flexDirection: "column", gap: 12, maxWidth: 320 }, children: [
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", { style: { margin: 0, fontSize: 14, color: "#374151" }, children: "Georgia U.S. Senate — 2026 general election" }),
      /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { style: { display: "flex", gap: 8 }, children: [
        /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ds_exports.Button, { variant: "primary", size: "md", children: "View Full Race Guide" }),
        /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ds_exports.Button, { variant: "secondary", size: "md", children: "Share" })
      ] })
    ] });
  }
  return __toCommonJS(Button_exports);
})();
