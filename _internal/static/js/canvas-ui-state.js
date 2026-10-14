/* Transient selection/editor state. Never part of the saved canvas payload. */
(function (global) {
    'use strict';

    function create() {
        let selection = Object.freeze({primaryId:'', ids:Object.freeze([]), image:Object.freeze({nodeId:'', index:-1})});
        let editor = Object.freeze({key:'', subject:null});
        let revision = 0;
        const transitions = [];

        function record(reason) {
            revision++;
            transitions.push(Object.freeze({revision, reason:String(reason || 'update'),
                primaryId:selection.primaryId, ids:selection.ids, image:selection.image,
                editorKey:editor.key, editorNodeId:editor.subject?.id || ''}));
            if (transitions.length > 40) transitions.shift();
        }

        function patchSelection(patch, reason) {
            patch = patch || {};
            const next = {...selection, ...patch};
            next.primaryId = String(next.primaryId || '');
            next.ids = Object.freeze([...new Set((Array.isArray(next.ids) ? next.ids : []).filter(Boolean))]);
            const image = next.image || {};
            next.image = Object.freeze({nodeId:String(image.nodeId || ''), index:Number.isInteger(image.index) ? image.index : -1});
            if (selection.primaryId === next.primaryId && selection.ids.length === next.ids.length &&
                selection.ids.every((id, i) => id === next.ids[i]) &&
                selection.image.nodeId === next.image.nodeId && selection.image.index === next.image.index) return selection;
            selection = Object.freeze(next);
            record(reason || 'selection');
            return selection;
        }

        function patchEditor(patch, reason) {
            const next = {...editor, ...(patch || {})};
            next.key = String(next.key || '');
            next.subject = next.subject || null;
            if (next.key === editor.key && next.subject === editor.subject) return editor;
            editor = Object.freeze(next);
            record(reason || 'editor');
            return editor;
        }

        function bindEditor(subject, key) { return patchEditor({subject, key}, 'bind-editor'); }
        function clearEditor() { return bindEditor(null, ''); }
        function snapshot() {
            return {revision, selection:{primaryId:selection.primaryId, ids:[...selection.ids], image:{...selection.image}},
                editor:{key:editor.key, nodeId:editor.subject?.id || ''}, transitions:transitions.slice()};
        }

        // Temporary adapter for existing debug tools/browser fixtures. It has
        // no backing state; production code uses the commands above directly.
        function installLegacyAliases(target) {
            const aliases = {
                selectedId:['selection', 'primaryId'], selectedIds:['selection', 'ids'], selectedImage:['selection', 'image'],
                activeComposerSubject:['editor', 'subject'], lastComposerNodeId:['editor', 'key']
            };
            Object.entries(aliases).forEach(([name, [domain, key]]) => {
                Object.defineProperty(target, name, {configurable:true,
                    get:() => domain === 'selection' ? selection[key] : editor[key],
                    set:value => domain === 'selection' ? patchSelection({[key]:value}, 'compat:' + name) : patchEditor({[key]:value}, 'compat:' + name)});
            });
        }

        return Object.freeze({get selection(){return selection;}, get editor(){return editor;},
            patchSelection, patchEditor, bindEditor, clearEditor, snapshot, installLegacyAliases});
    }

    global.CanvasUiState = {create};
})(typeof window !== 'undefined' ? window : globalThis);
