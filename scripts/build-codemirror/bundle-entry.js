// Core state & view
export {
    EditorState,
    Compartment,
    RangeSetBuilder,
    StateField,
    StateEffect,
    Prec,
} from '@codemirror/state';

export {
    EditorView,
    keymap,
    lineNumbers,
    highlightActiveLine,
    highlightActiveLineGutter,
    Decoration,
    ViewPlugin,
    WidgetType,
    GutterMarker,
    gutter,
} from '@codemirror/view';

// Commands
export {
    defaultKeymap,
    indentWithTab,
    history,
    historyKeymap,
    undo,
} from '@codemirror/commands';

// Language support
export {
    syntaxHighlighting,
    HighlightStyle,
    defaultHighlightStyle,
    indentUnit,
} from '@codemirror/language';

export { tags } from '@lezer/highlight';

// Language packs
export { python } from '@codemirror/lang-python';
export { javascript } from '@codemirror/lang-javascript';
export { html } from '@codemirror/lang-html';
export { css } from '@codemirror/lang-css';
export { json } from '@codemirror/lang-json';
export { markdown } from '@codemirror/lang-markdown';
export { yaml } from '@codemirror/lang-yaml';

// R via legacy CodeMirror 5 stream parser - no Lezer parser exists for R
import { StreamLanguage } from '@codemirror/language';
import { r as rLegacy } from '@codemirror/legacy-modes/mode/r';
const r = () => StreamLanguage.define(rLegacy);
export { r };

// Lint & Diagnostics
export {
    lintGutter,
    setDiagnostics,
    linter,
    diagnosticCount,
    forEachDiagnostic,
} from '@codemirror/lint';

// Autocomplete
export {
    autocompletion,
    completionKeymap,
} from '@codemirror/autocomplete';

// LSP client
export {
    languageServer,
    jumpToDefinition,
    languageServerPlugin,
} from 'codemirror-languageserver';

// Minimap
export { showMinimap } from '@replit/codemirror-minimap';

// Themes
export { oneDark } from '@codemirror/theme-one-dark';
export { ayuLight, clouds, espresso, smoothy, tomorrow } from 'thememirror';
