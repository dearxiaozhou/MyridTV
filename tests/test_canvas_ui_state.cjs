'use strict';
const assert = require('node:assert/strict');
require('../_internal/static/js/canvas-ui-state.js');

const state = global.CanvasUiState.create();
state.patchSelection({primaryId:'a', ids:['a','b'], image:{nodeId:'a',index:0}}, 'select-test');
assert.equal(state.snapshot().revision, 1);
assert.equal(state.snapshot().transitions.length, 1);
assert.equal(state.selection.primaryId, 'a');
assert.deepEqual(state.selection.ids, ['a','b']);
assert.throws(() => { state.selection.ids.push('bypass'); }, TypeError);
assert.throws(() => { state.selection.primaryId = 'bypass'; }, TypeError);
const snapshot = state.snapshot();
snapshot.selection.ids.push('snapshot-only');
snapshot.selection.image.nodeId = 'snapshot-only';
assert.deepEqual(state.selection.ids, ['a','b']);
assert.equal(state.selection.image.nodeId, 'a');

const node = {id:'a', promptDraftText:'private draft'};
state.bindEditor(node, 'a:node');
assert.equal(state.editor.subject, node);
assert.equal(state.snapshot().editor.nodeId, 'a');
assert.equal(JSON.stringify(state.snapshot()).includes('private draft'), false);
state.clearEditor();
assert.equal(state.editor.subject, null);
assert.equal(state.editor.key, '');
assert.equal(node.promptDraftText, 'private draft');

const aliases = {};
state.installLegacyAliases(aliases);
aliases.selectedId = 'legacy';
assert.equal(state.selection.primaryId, 'legacy');
state.patchSelection({primaryId:'command'}, 'command');
assert.equal(aliases.selectedId, 'command');
const revision = state.snapshot().revision;
state.patchSelection({primaryId:'command'}, 'no-change');
assert.equal(state.snapshot().revision, revision);
console.log('PASS - atomic selection, immutable snapshots, editor ownership, diagnostics and compatibility');
