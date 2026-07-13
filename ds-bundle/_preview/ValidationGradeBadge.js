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

  // .design-sync/previews/ValidationGradeBadge.tsx
  var ValidationGradeBadge_exports = {};
  __export(ValidationGradeBadge_exports, {
    DarkBackground: () => DarkBackground,
    GradeSweep: () => GradeSweep,
    InCandidateHeader: () => InCandidateHeader
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

  // .design-sync/previews/ValidationGradeBadge.tsx
  var import_jsx_runtime = __toESM(require_react_shim());
  function GradeSweep() {
    return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { style: { display: "flex", gap: 12, flexWrap: "wrap" }, children: [
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
        ds_exports.ValidationGradeBadge,
        {
          grade: { grade: "A", score: 94, summary: "Comprehensive sourcing with strong cross-verification across issue stances." }
        }
      ),
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
        ds_exports.ValidationGradeBadge,
        {
          grade: { grade: "B", score: 78, summary: "Well sourced with some gaps in donor disclosure." }
        }
      ),
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
        ds_exports.ValidationGradeBadge,
        {
          grade: { grade: "C", score: 61, summary: "Adequate coverage, but several stances rely on a single secondary source." }
        }
      ),
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
        ds_exports.ValidationGradeBadge,
        {
          grade: { grade: "D", score: 44, summary: "Sparse sourcing on voting record; primary sources largely unavailable." }
        }
      ),
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
        ds_exports.ValidationGradeBadge,
        {
          grade: { grade: "F", score: 22, summary: "Insufficient verifiable data to support most claims in this profile." }
        }
      )
    ] });
  }
  function InCandidateHeader() {
    return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { style: { maxWidth: 480, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16 }, children: [
      /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [
        /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { style: { fontWeight: 700, fontSize: 18, color: "#111827" }, children: "Sarah Whitfield" }),
        /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { style: { fontSize: 13, color: "#6b7280" }, children: "Democrat · Georgia Senate 2026" })
      ] }),
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ds_exports.ValidationGradeBadge, { grade: { grade: "B", score: 82, summary: "Well sourced with some gaps in donor disclosure." } })
    ] });
  }
  function DarkBackground() {
    return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(
      "div",
      {
        className: "dark",
        style: { background: "#030712", padding: 20, borderRadius: 12, display: "flex", gap: 12, flexWrap: "wrap" },
        children: [
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
            ds_exports.ValidationGradeBadge,
            {
              grade: { grade: "A", score: 91, summary: "Comprehensive sourcing with strong cross-verification." }
            }
          ),
          /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
            ds_exports.ValidationGradeBadge,
            {
              grade: { grade: "C", score: 58, summary: "Adequate coverage, but several stances rely on a single source." }
            }
          )
        ]
      }
    );
  }
  return __toCommonJS(ValidationGradeBadge_exports);
})();
