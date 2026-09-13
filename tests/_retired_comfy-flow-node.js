/* 工作流卡片节点（comfy-flow）
 * ---------------------------------------------------------------------------
 * 一个工作流 = 画布上的一张卡片。卡内列出工作流的全部节点，每个节点可以
 * 单独切换「执行 / 旁路 / 禁用」，点开可以直接改参数。
 *
 * 为什么要自己算 bypass：ComfyUI 的 /prompt 接口不认识节点上的 mode 字段，
 * 旁路是它前端 JS 算出来的。真正的图改写发生在后端 comfy_flow_compiler，
 * 这里只负责把用户的开关意图提交过去。
 *
 * 本文件故意做成独立模块：只包装 smart-canvas.js 暴露的少数几个函数，
 * 不改动它的主体逻辑，降低与其它改动撞车的概率。
 */
(function(){
    'use strict';

    var CF = {
        flows: {},          // 工作流名 -> {workflow, objectInfo, nodes, error}
        pending: {},        // 正在加载的工作流名
        polls: {},          // node id -> timer
        booted: false
    };

    var DEFAULT_W = 380;
    var DEFAULT_H = 520;

    function esc(value){
        if(typeof escapeHtml === 'function') return escapeHtml(String(value ?? ''));
        return String(value ?? '').replace(/[&<>"']/g, function(c){
            return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
        });
    }
    function notify(message){
        if(typeof toast === 'function') toast(String(message).slice(0, 200));
    }
    function repaint(){
        if(typeof render === 'function') render();
    }
    function persist(){
        if(typeof scheduleSave === 'function') scheduleSave();
    }
    function proxyUrl(path){
        if(typeof comfyProxyUrl === 'function') return comfyProxyUrl(path);
        return path;
    }
    function isFlowNode(node){
        return Boolean(node) && node.type === 'comfy-flow';
    }
    // nodes / viewport 是 smart-canvas.js 顶层的 let 声明：不挂在 window 上，
    // 但同属全局词法环境，后加载的脚本可以直接按标识符访问。
    function nodeList(){
        try { return (typeof nodes !== 'undefined' && Array.isArray(nodes)) ? nodes : []; }
        catch(e) { return []; }
    }
    function findNode(id){
        return nodeList().find(function(n){ return n.id === id; }) || null;
    }
    function createNode(node){
        if(typeof nodeStore !== 'undefined' && nodeStore && typeof nodeStore.addNode === 'function'){
            return nodeStore.addNode(node, 'user');
        }
        var list = nodeList();
        list.push(node);
        return node;
    }

    // ---------------------------------------------------------------------
    // 样式
    // ---------------------------------------------------------------------
    function injectStyles(){
        if(document.getElementById('comfy-flow-node-css')) return;
        var style = document.createElement('style');
        style.id = 'comfy-flow-node-css';
        style.textContent = [
            '.cf-card{display:flex;flex-direction:column;height:100%;font-size:12px;line-height:1.5;overflow:hidden}',
            '.cf-head{display:flex;align-items:center;gap:6px;padding:8px 10px;border-bottom:1px solid rgba(128,128,128,.28)}',
            '.cf-name{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:500}',
            '.cf-run{border:1px solid rgba(128,128,128,.4);background:transparent;color:inherit;border-radius:6px;padding:3px 10px;cursor:pointer;font-size:11px}',
            '.cf-run:hover{background:rgba(128,128,128,.16)}',
            '.cf-run.is-busy{border-color:#d08a2a;color:#d08a2a}',
            '.cf-status{padding:5px 10px;font-size:11px;opacity:.8;border-bottom:1px solid rgba(128,128,128,.18)}',
            '.cf-status.is-error{color:#e05a4a;opacity:1}',
            '.cf-bar{height:3px;background:rgba(128,128,128,.2);overflow:hidden}',
            '.cf-bar > i{display:block;height:100%;background:#4a9eff;transition:width .3s}',
            '.cf-list{flex:1;overflow-y:auto;padding:4px 0}',
            '.cf-row{display:flex;align-items:center;gap:6px;padding:4px 10px;cursor:default}',
            '.cf-row:hover{background:rgba(128,128,128,.1)}',
            '.cf-row.is-bypass{background:rgba(217,119,6,.16)}',
            '.cf-row.is-mute{opacity:.45;text-decoration:line-through}',
            '.cf-row.is-running{background:rgba(74,158,255,.18)}',
            '.cf-row-title{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
            '.cf-row-out{font-size:10px;opacity:.6;border:1px solid rgba(128,128,128,.4);border-radius:4px;padding:0 3px}',
            '.cf-seg{display:flex;border:1px solid rgba(128,128,128,.4);border-radius:5px;overflow:hidden;flex:none}',
            '.cf-seg button{border:0;background:transparent;color:inherit;font-size:10px;padding:2px 5px;cursor:pointer;opacity:.55}',
            '.cf-seg button.is-on{opacity:1;background:rgba(128,128,128,.28);font-weight:500}',
            '.cf-seg button.is-on[data-cf-mode="bypass"]{background:rgba(217,119,6,.32)}',
            '.cf-seg button.is-on[data-cf-mode="mute"]{background:rgba(224,90,74,.32)}',
            '.cf-toggle{width:16px;flex:none;text-align:center;cursor:pointer;opacity:.6;border:0;background:transparent;color:inherit;font-size:10px}',
            '.cf-params{padding:2px 10px 8px 22px;display:flex;flex-direction:column;gap:5px}',
            '.cf-param{display:flex;flex-direction:column;gap:2px}',
            '.cf-param > label{font-size:10px;opacity:.65}',
            '.cf-param input,.cf-param select,.cf-param textarea{width:100%;box-sizing:border-box;background:rgba(128,128,128,.12);border:1px solid rgba(128,128,128,.3);color:inherit;border-radius:4px;padding:2px 5px;font-size:11px;font-family:inherit}',
            '.cf-param textarea{min-height:44px;resize:vertical}',
            '.cf-param .cf-link{font-size:10px;opacity:.5;font-style:italic}',
            '.cf-shots{display:flex;gap:4px;padding:6px 10px;flex-wrap:wrap;border-top:1px solid rgba(128,128,128,.18)}',
            '.cf-shots img{width:64px;height:64px;object-fit:cover;border-radius:5px;border:1px solid rgba(128,128,128,.3);cursor:pointer}',
            '.cf-empty{padding:14px 10px;text-align:center;opacity:.55}',
            '.cf-hint{padding:6px 10px;font-size:10px;opacity:.45;border-top:1px solid rgba(128,128,128,.14)}',
            '.cf-more{display:flex;align-items:center;gap:6px;padding:5px 10px;font-size:10px;opacity:.65;cursor:pointer;border-top:1px dashed rgba(128,128,128,.22);margin-top:4px}',
            '.cf-more:hover{opacity:1}',
            '.cf-more.is-open{opacity:1}',
            '.cf-rest{border-top:1px dashed rgba(128,128,128,.14)}',
            /* 卡片是内容型节点：.image-node 默认透明（为图片节点设计），这里补面板底 */
            '.image-node:has(.cf-card){padding:12px;box-sizing:border-box;background:var(--panel);border:1px solid var(--line);box-shadow:0 20px 56px var(--shadow);backdrop-filter:blur(20px);overflow:visible;}',
            '.image-node:has(.cf-card) .node-body{padding:0;height:100%;min-height:0;align-items:stretch;justify-content:stretch;}',
            '.cf-picker-backdrop{position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:99999;display:flex;align-items:center;justify-content:center}',
            '.cf-picker{background:var(--panel-bg,#24262b);color:var(--panel-text,#e8e8ea);border:1px solid rgba(128,128,128,.4);border-radius:10px;min-width:340px;max-width:480px;max-height:70vh;display:flex;flex-direction:column;box-shadow:0 12px 40px rgba(0,0,0,.5)}',
            '.cf-picker h4{margin:0;padding:12px 14px;border-bottom:1px solid rgba(128,128,128,.28);font-size:13px;font-weight:600}',
            '.cf-picker-list{overflow-y:auto;padding:6px}',
            '.cf-picker-item{display:flex;align-items:center;gap:8px;width:100%;text-align:left;background:transparent;border:0;color:inherit;padding:8px 10px;border-radius:6px;cursor:pointer;font-size:12px}',
            '.cf-picker-item:hover{background:rgba(128,128,128,.18)}',
            '.cf-wf-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;width:100%;padding:12px;overflow-y:auto;align-content:start}',
            '.cf-wf-card{border:1px solid rgba(128,128,128,.35);border-radius:8px;padding:10px;display:flex;flex-direction:column;gap:8px;background:rgba(128,128,128,.08)}',
            '.cf-wf-name{font-size:12px;font-weight:500;line-height:1.35;word-break:break-all}',
            '.cf-wf-add{align-self:flex-start;border:1px solid rgba(74,158,255,.55);color:#4a9eff;background:transparent;border-radius:6px;padding:3px 10px;cursor:pointer;font-size:11px}',
            '.cf-wf-add:hover{background:rgba(74,158,255,.15)}'
        ].join('\n');
        document.head.appendChild(style);
    }

    // ---------------------------------------------------------------------
    // 数据：工作流 + 节点元数据
    // ---------------------------------------------------------------------
    function describeNodes(workflow, objectInfo, prefs){
        var referenced = {};
        Object.keys(workflow || {}).forEach(function(id){
            var inputs = (workflow[id] || {}).inputs || {};
            Object.keys(inputs).forEach(function(key){
                var value = inputs[key];
                if(Array.isArray(value) && value.length === 2 && typeof value[0] === 'string' && Number.isInteger(value[1])){
                    referenced[value[0]] = true;
                }
            });
        });
        return Object.keys(workflow || {})
            .sort(function(a, b){ return (parseInt(a, 10) || 0) - (parseInt(b, 10) || 0); })
            .map(function(id){
                var node = workflow[id] || {};
                var classType = String(node.class_type || '');
                var info = (objectInfo || {})[classType] || {};
                var pref = (prefs || {})[id] || {};
                var metaTitle = String((node._meta || {}).title || '').trim();
                var isOutput = !referenced[id] && (classType.indexOf('Save') === 0 || classType.indexOf('Preview') === 0);
                return {
                    id: id,
                    classType: classType,
                    title: String(pref.name || metaTitle || info.display_name || classType),
                    isOutput: isOutput,
                    hidden: Boolean(pref.hidden)
                };
            })
            .filter(function(item){ return !item.hidden; });
    }

    function ensureFlowData(node){
        var name = String(node.comfyWorkflow || '').trim();
        if(!name) return null;
        if(CF.flows[name]) return CF.flows[name];
        if(CF.pending[name]) return {loading: true};

        CF.pending[name] = true;
        var entry = {loading: true, workflow: null, objectInfo: {}, nodes: [], error: ''};
        CF.flows[name] = entry;

        fetch(proxyUrl('/api/workflows/' + encodeURIComponent(name)))
            .then(function(r){
                if(!r.ok) return r.text().then(function(t){ throw new Error(t || ('HTTP ' + r.status)); });
                return r.json();
            })
            .then(function(data){
                var workflow = (data && data.workflow) || {};
                var config = (data && data.config) || {};
                var types = Object.keys(workflow).map(function(id){ return String((workflow[id] || {}).class_type || ''); })
                    .filter(Boolean);
                var unique = types.filter(function(t, i){ return types.indexOf(t) === i; });
                var query = unique.length ? '?types=' + encodeURIComponent(unique.join(',')) : '';
                return fetch(proxyUrl('/api/comfyui/object-info' + query))
                    .then(function(r){ return r.ok ? r.json() : {object_info: {}}; })
                    .then(function(oi){
                        entry.workflow = workflow;
                        entry.config = config;
                        entry.objectInfo = (oi && oi.object_info) || {};
                        entry.nodes = describeNodes(workflow, entry.objectInfo, node.comfyPrefs);
                        entry.loading = false;
                        delete CF.pending[name];
                        repaint();
                    });
            })
            .catch(function(err){
                entry.loading = false;
                entry.error = String(err.message || err).slice(0, 160);
                delete CF.pending[name];
                repaint();
            });
        return entry;
    }

    // ---------------------------------------------------------------------
    // 参数面板
    // ---------------------------------------------------------------------
    // config.fields（设置页里配的“暴露字段”）→ { 节点id: [{input, label}] }
    // 卡片只显示这里涉及到的节点与字段；没配过的退回显示全部。
    function exposedMap(config){
        var map = {};
        ((config && config.fields) || []).forEach(function(f){
            if(!f || f.node === undefined || f.node === null) return;
            var id = String(f.node);
            (map[id] = map[id] || []).push({
                input: String(f.input || ''),
                label: String(f.name || f.input || '')
            });
        });
        return map;
    }

    function isLinkValue(value){
        return Array.isArray(value) && value.length === 2
            && typeof value[0] === 'string' && Number.isInteger(value[1]);
    }

    function controlHtml(node, nodeId, key, spec, labelOverride){
        var info = (CF.flows[String(node.comfyWorkflow || '')] || {}).objectInfo || {};
        var workflow = (CF.flows[String(node.comfyWorkflow || '')] || {}).workflow || {};
        var inputs = (workflow[nodeId] || {}).inputs || {};
        var current = inputs[key];
        var overrides = (node.comfyOverrides || {})[nodeId] || {};
        if(Object.prototype.hasOwnProperty.call(overrides, key)) current = overrides[key];
        if(isLinkValue(current)) return '';

        var head = Array.isArray(spec) ? spec[0] : null;
        var opts = (Array.isArray(spec) && spec[1] && typeof spec[1] === 'object') ? spec[1] : {};
        var attrs = 'data-cf-param="' + esc(nodeId + '::' + key) + '"';
        var labelText = String(labelOverride || key);

        if(Array.isArray(head)){
            var options = head.map(function(o){
                var label = String(o && typeof o === 'object' ? (o.name || o.content || JSON.stringify(o)) : o);
                var value = String(o && typeof o === 'object' ? (o.content || o.name || '') : o);
                return '<option value="' + esc(value) + '"' + (value === String(current) ? ' selected' : '') + '>' + esc(label) + '</option>';
            }).join('');
            return '<div class="cf-param"><label>' + esc(labelText) + '</label><select ' + attrs + '>' + options + '</select></div>';
        }
        if(head === 'INT' || head === 'FLOAT'){
            var min = Number.isFinite(opts.min) ? opts.min : '';
            var max = Number.isFinite(opts.max) ? opts.max : '';
            var step = Number.isFinite(opts.step) ? opts.step : (head === 'INT' ? 1 : 0.01);
            return '<div class="cf-param"><label>' + esc(labelText) + (max !== '' ? ' <span style="opacity:.5">(' + esc(min) + '~' + esc(max) + ')</span>' : '') + '</label>'
                + '<input type="number" ' + attrs + ' value="' + esc(current ?? '') + '"'
                + (min !== '' ? ' min="' + esc(min) + '"' : '') + (max !== '' ? ' max="' + esc(max) + '"' : '')
                + ' step="' + esc(step) + '"></div>';
        }
        if(head === 'BOOLEAN'){
            return '<div class="cf-param"><label style="display:flex;align-items:center;gap:5px">'
                + '<input type="checkbox" ' + attrs + (current ? ' checked' : '') + ' style="width:auto">' + esc(labelText) + '</label></div>';
        }
        if(head === 'STRING'){
            if(opts.multiline){
                return '<div class="cf-param"><label>' + esc(labelText) + '</label><textarea ' + attrs + '>' + esc(current ?? '') + '</textarea></div>';
            }
            return '<div class="cf-param"><label>' + esc(labelText) + '</label><input type="text" ' + attrs + ' value="' + esc(current ?? '') + '"></div>';
        }
        return '<div class="cf-param"><label>' + esc(labelText) + '</label><span class="cf-link">由连线提供 (' + esc(head) + ')</span></div>';
    }

    // allowed: {inputKey: label} —— 暴露节点只渲染 config 声明的字段；null = 全部
    function paramsHtml(node, nodeId, allowed){
        var entry = CF.flows[String(node.comfyWorkflow || '')] || {};
        var workflow = entry.workflow || {};
        var info = entry.objectInfo || {};
        var classType = String((workflow[nodeId] || {}).class_type || '');
        var spec = (info[classType] || {}).input || {};
        var order = [].concat(Object.keys(spec.required || {}), Object.keys(spec.optional || {}));
        if(allowed) order = order.filter(function(key){ return Object.prototype.hasOwnProperty.call(allowed, key); });
        return order.map(function(key){
            return controlHtml(node, nodeId, key, (spec.required || {})[key] || (spec.optional || {})[key],
                allowed ? allowed[key] : '');
        }).join('');
    }

    // ---------------------------------------------------------------------
    // 渲染
    // ---------------------------------------------------------------------
    function nodeRowHtml(node, item, job, exposedFields){
        var modes = node.comfyModes || {};
        var mode = modes[item.id] || 'run';
        var expanded = Boolean((node.comfyExpanded || {})[item.id]);
        var running = job && item.id === String(job.current_node || '');
        var segments = ['run', 'bypass', 'mute'].map(function(m){
            var label = m === 'run' ? '执行' : (m === 'bypass' ? '旁路' : '禁用');
            return '<button type="button" data-cf-act="mode" data-cf-node="' + esc(node.id) + '" data-cf-id="' + esc(item.id)
                + '" data-cf-mode="' + m + '" class="' + (mode === m ? 'is-on' : '') + '" title="'
                + (m === 'bypass' ? '跳过该节点，下游改接它的上游' : (m === 'mute' ? '删除该节点及其全部下游' : '正常执行'))
                + '">' + label + '</button>';
        }).join('');
        var classes = ['cf-row'];
        if(mode === 'bypass') classes.push('is-bypass');
        if(mode === 'mute') classes.push('is-mute');
        if(running) classes.push('is-running');
        // 暴露节点：参数只显示 config 声明的字段（labels 来自设置页里配的名字）
        var allowed = null;
        if(exposedFields && exposedFields.length){
            allowed = {};
            exposedFields.forEach(function(f){
                if(f.input) allowed[f.input] = f.label || f.input;
            });
        }
        return '<div class="' + classes.join(' ') + '">'
            + '<button type="button" class="cf-toggle" data-cf-act="expand" data-cf-node="' + esc(node.id) + '" data-cf-id="' + esc(item.id) + '">'
            + (expanded ? '\u25BE' : '\u25B8') + '</button>'
            + '<span class="cf-row-title" title="' + esc(item.classType) + '">' + esc(item.id) + ' \u00b7 ' + esc(item.title) + '</span>'
            + (item.isOutput ? '<span class="cf-row-out">输出</span>' : '')
            + '<span class="cf-seg">' + segments + '</span>'
            + '</div>'
            + (expanded ? '<div class="cf-params">' + (paramsHtml(node, item.id, allowed) || '<span class="cf-link">该节点没有可编辑参数</span>') + '</div>' : '');
    }

    function cfNodeBodyHtml(node, layout){
        var name = String(node.comfyWorkflow || '').trim();
        if(!name){
            return '<div class="cf-empty">未绑定工作流</div>';
        }
        var entry = ensureFlowData(node);
        var job = node.comfyJob || null;
        var busy = Boolean(job && (job.status === 'queued' || job.status === 'running'));

        var head = '<div class="cf-head"><span class="cf-name">' + esc(node.title || name.replace(/\.json$/i, '')) + '</span>'
            + (busy
                ? '<button type="button" class="cf-run is-busy" data-cf-act="cancel" data-cf-node="' + esc(node.id) + '">停止</button>'
                : '<button type="button" class="cf-run" data-cf-act="run" data-cf-node="' + esc(node.id) + '">运行</button>')
            + '</div>';

        if(!entry || entry.loading){
            return head + '<div class="cf-empty">正在读取工作流\u2026</div>';
        }
        if(entry.error){
            return head + '<div class="cf-status is-error">读取失败：' + esc(entry.error) + '</div>';
        }

        var status = '';
        if(job){
            var text = {queued: '排队中', running: '运行中', done: '已完成', error: '失败', cancelled: '已取消', gone: '任务已丢失'}[job.status] || job.status;
            if(job.status === 'running' && job.current_node_title) text += ' \u00b7 ' + job.current_node_title;
            if(job.status === 'error' && job.error) text += '：' + job.error;
            if(job.elapsed && job.status !== 'running') text += '（' + job.elapsed + 's）';
            status = '<div class="cf-status' + (job.status === 'error' ? ' is-error' : '') + '">' + esc(text) + '</div>'
                + (busy ? '<div class="cf-bar"><i style="width:' + (Number(job.progress) || 0) + '%"></i></div>' : '');
        }

        // config.fields 声明过的节点 = 暴露节点（主清单）；其余收进折叠区。
        // 没配置 fields 的老工作流退回显示全部。
        var expMap = exposedMap(entry.config || {});
        var expIds = Object.keys(expMap);
        var nodes = entry.nodes || [];
        var visible = nodes, rest = [];
        if(expIds.length){
            visible = nodes.filter(function(item){ return expMap[item.id]; });
            rest = nodes.filter(function(item){ return !expMap[item.id]; });
            if(!visible.length){ visible = nodes; rest = []; } // 配置过期，兜底显示全部
        }

        var rows = visible.map(function(item){ return nodeRowHtml(node, item, job, expMap[item.id] || null); }).join('')
            || '<div class="cf-empty">工作流里没有节点</div>';

        if(rest.length){
            rows += '<div class="cf-more' + (node.comfyShowRest ? ' is-open' : '') + '" data-cf-act="rest" data-cf-node="' + esc(node.id) + '">'
                + (node.comfyShowRest ? '\u25BE' : '\u25B8') + ' 其余 ' + rest.length + ' 个节点'
                + (node.comfyShowRest ? '' : '（点开可旁路/禁用任意节点）') + '</div>'
                + (node.comfyShowRest ? '<div class="cf-rest">' + rest.map(function(item){
                    return nodeRowHtml(node, item, job, null);
                }).join('') + '</div>' : '');
        }
        if(!expIds.length){
            rows += '<div class="cf-hint">提示：在 ComfyUI 设置里给工作流配置暴露字段，卡片就只显示那些节点</div>';
        }
        var shots = ((node.images || []).length)
            ? '<div class="cf-shots">' + node.images.slice(-6).map(function(img){
                return '<img src="' + esc(img.url) + '" alt="">';
            }).join('') + '</div>'
            : '';

        return '<div class="cf-card">' + head + status + '<div class="cf-list">' + rows + '</div>' + shots + '</div>';
    }

    // ---------------------------------------------------------------------
    // 运行与轮询
    // ---------------------------------------------------------------------
    function stopPolling(nodeId){
        if(CF.polls[nodeId]){
            clearTimeout(CF.polls[nodeId]);
            delete CF.polls[nodeId];
        }
    }

    function pollJob(nodeId){
        var node = findNode(nodeId);
        if(!node || !node.comfyJob) { stopPolling(nodeId); return; }
        var jobId = node.comfyJob.job_id;
        var previous = node.comfyJob.status + '/' + node.comfyJob.progress + '/' + (node.comfyJob.current_node || '');

        fetch(proxyUrl('/api/comfyui/jobs/' + encodeURIComponent(jobId)))
            .then(function(r){
                if(r.status === 404) return null;
                if(!r.ok) throw new Error('HTTP ' + r.status);
                return r.json();
            })
            .then(function(data){
                var nodeNow = findNode(nodeId);
                if(!nodeNow) { stopPolling(nodeId); return; }
                if(!data){
                    nodeNow.comfyJob = {job_id: jobId, status: 'gone', error: '任务不存在或已过期'};
                    stopPolling(nodeId);
                    repaint();
                    return;
                }
                nodeNow.comfyJob = {
                    job_id: data.job_id || jobId,
                    status: data.status,
                    progress: data.progress,
                    current_node: data.current_node,
                    current_node_title: data.current_node_title,
                    error: data.error,
                    elapsed: data.elapsed
                };
                if(data.status === 'done'){
                    nodeNow.images = (data.images || []).map(function(url){ return {url: url}; }).concat(nodeNow.images || []);
                    stopPolling(nodeId);
                    persist();
                } else if(data.status === 'error' || data.status === 'cancelled'){
                    stopPolling(nodeId);
                }
                var now = nodeNow.comfyJob.status + '/' + nodeNow.comfyJob.progress + '/' + (nodeNow.comfyJob.current_node || '');
                if(now !== previous || data.status !== 'running') repaint();
                if(data.status === 'running' || data.status === 'queued'){
                    CF.polls[nodeId] = setTimeout(function(){ pollJob(nodeId); }, 2000);
                }
            })
            .catch(function(err){
                var nodeNow = findNode(nodeId);
                if(nodeNow){
                    nodeNow.comfyJob = nodeNow.comfyJob || {};
                    nodeNow.comfyJob.error = String(err.message || err).slice(0, 160);
                    repaint();
                }
                CF.polls[nodeId] = setTimeout(function(){ pollJob(nodeId); }, 5000);
            });
    }

    function runFlowNode(node){
        if(!node) return;
        var name = String(node.comfyWorkflow || '').trim();
        if(!name){ notify('卡片没有绑定工作流'); return; }
        var entry = CF.flows[name];
        if(!entry || entry.loading){ notify('工作流还没读完，稍等一下'); return; }

        node.comfyJob = {job_id: '', status: 'queued', progress: 0, current_node: '', error: ''};
        repaint();

        fetch(proxyUrl('/api/comfyui/jobs'), {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                workflow: name,
                overrides: node.comfyOverrides || {},
                modes: node.comfyModes || {},
                prefs: node.comfyPrefs || {}
            })
        })
            .then(function(r){ return r.json().then(function(d){ return {ok: r.ok, data: d}; }); })
            .then(function(res){
                if(!res.ok || !res.data.ok){ throw new Error((res.data && res.data.error) || '提交失败'); }
                node.comfyJob = {
                    job_id: res.data.job_id,
                    status: res.data.status,
                    progress: res.data.progress,
                    current_node: res.data.current_node,
                    current_node_title: res.data.current_node_title,
                    error: ''
                };
                stopPolling(node.id);
                pollJob(node.id);
                repaint();
            })
            .catch(function(err){
                node.comfyJob = {job_id: '', status: 'error', error: String(err.message || err).slice(0, 200)};
                notify(node.comfyJob.error);
                repaint();
            });
    }

    function cancelFlowNode(node){
        if(!node || !node.comfyJob || !node.comfyJob.job_id) return;
        fetch(proxyUrl('/api/comfyui/jobs/' + encodeURIComponent(node.comfyJob.job_id) + '/cancel'), {method: 'POST'})
            .then(function(){ stopPolling(node.id); })
            .catch(function(){});
        node.comfyJob.status = 'cancelled';
        repaint();
    }

    // ---------------------------------------------------------------------
    // 创建卡片
    // ---------------------------------------------------------------------
    function createFlowNode(workflowName){
        var name = String(workflowName || '').trim();
        if(!name) return null;
        var x = 200, y = 200;
        try {
            var vp = (typeof viewport !== 'undefined' && viewport) ? viewport : {x: 0, y: 0, scale: 1};
            var scale = Number(vp.scale) || 1;
            var cx = (window.innerWidth / 2 - Number(vp.x || 0)) / scale - DEFAULT_W / 2;
            var cy = (window.innerHeight / 2 - Number(vp.y || 0)) / scale - DEFAULT_H / 2;
            if(Number.isFinite(cx) && Number.isFinite(cy)){ x = Math.round(cx); y = Math.round(cy); }
        } catch(e) { /* 视口算不出来就用默认位置 */ }
        var node = {
            id: 'node_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
            type: 'comfy-flow',
            title: name.replace(/\.json$/i, ''),
            comfyWorkflow: name,
            comfyModes: {},
            comfyOverrides: {},
            comfyExpanded: {},
            comfyPrefs: {},
            images: [],
            x: x,
            y: y,
            w: DEFAULT_W,
            h: DEFAULT_H,
            status: 'ready',
            role: 'generation'
        };
        if(!createNode(node)) { notify('创建卡片失败'); return null; }
        ensureFlowData(node);
        repaint();
        persist();
        return node;
    }

    // ---------------------------------------------------------------------
    // 创建入口：工作流选择器
    // ---------------------------------------------------------------------
    function workflowsListPromise(){
        // smart-canvas.js 维护的 comfyWorkflows 全局在多数场景已加载好，
        // 直接复用；为空（如刚开页还没拉完）就自己请求一次。
        try {
            if(typeof comfyWorkflows !== 'undefined' && Array.isArray(comfyWorkflows) && comfyWorkflows.length){
                return Promise.resolve(comfyWorkflows.slice());
            }
        } catch(e) {}
        return fetch(proxyUrl('/api/workflows'))
            .then(function(r){ return r.ok ? r.json() : {workflows: []}; })
            .then(function(d){ return Array.isArray(d.workflows) ? d.workflows : []; })
            .catch(function(){ return []; });
    }

    function closePicker(){
        var backdrop = document.getElementById('cf-picker-backdrop');
        if(backdrop) backdrop.remove();
    }

    function openWorkflowPicker(){
        closePicker();
        var backdrop = document.createElement('div');
        backdrop.id = 'cf-picker-backdrop';
        backdrop.className = 'cf-picker-backdrop';
        backdrop.innerHTML = '<div class="cf-picker"><h4>选择 ComfyUI 工作流</h4>'
            + '<div class="cf-picker-list"><div class="cf-empty">正在读取工作流列表…</div></div></div>';
        backdrop.addEventListener('click', function(event){
            if(event.target === backdrop) closePicker();
        });
        document.body.appendChild(backdrop);

        workflowsListPromise().then(function(list){
            var listEl = backdrop.querySelector('.cf-picker-list');
            if(!listEl) return;
            if(!list.length){
                listEl.innerHTML = '<div class="cf-empty">没有可用的工作流</div>';
                return;
            }
            listEl.innerHTML = list.map(function(w){
                var name = String(w && (w.name || '') || '');
                var label = String((w && (w.title || '')) || name.replace(/\.json$/i, ''));
                return '<button type="button" class="cf-picker-item" data-cf-act="create-card" data-cf-workflow="'
                    + esc(name) + '"><i data-lucide="workflow"></i><span>' + esc(label) + '</span></button>';
            }).join('');
            if(typeof refreshIcons === 'function'){
                try { refreshIcons(); } catch(e) {}
            }
        });
    }

    // 资产库「工作流」tab：原本是个占位符，这里填成可点击的卡片列表
    function renderWorkflowTab(){
        var host = document.getElementById('workflowEmpty');
        if(!host) return;
        if(typeof assetTab === 'undefined' || assetTab !== 'workflow') return;
        host.innerHTML = '<div class="cf-wf-grid"><div class="cf-empty" style="grid-column:1/-1">正在读取工作流列表…</div></div>';
        workflowsListPromise().then(function(list){
            var grid = host.querySelector('.cf-wf-grid');
            if(!grid) return;
            if(!list.length){
                grid.innerHTML = '<div class="cf-empty" style="grid-column:1/-1">没有可用的工作流，先在 ComfyUI 设置里导入</div>';
                return;
            }
            grid.innerHTML = list.map(function(w){
                var name = String(w && (w.name || '') || '');
                var label = String((w && (w.title || '')) || name.replace(/\.json$/i, ''));
                return '<div class="cf-wf-card"><div class="cf-wf-name">' + esc(label) + '</div>'
                    + '<button type="button" class="cf-wf-add" data-cf-act="create-card" data-cf-workflow="' + esc(name) + '">添加为卡片</button></div>';
            }).join('');
        });
    }

    // ---------------------------------------------------------------------
    // 事件委托（捕获阶段，抢在画布的拖拽/选中之前）
    // ---------------------------------------------------------------------
    function bindEvents(){
        document.addEventListener('click', function(event){
            var target = event.target.closest ? event.target.closest('[data-cf-act]') : null;
            if(!target) return;
            event.preventDefault();
            event.stopPropagation();
            var act = target.dataset.cfAct;
            if(act === 'create-card'){
                // 选择器 / 资产库按钮没有 data-cf-node，必须在 findNode 之前处理
                closePicker();
                createFlowNode(target.dataset.cfWorkflow);
                return;
            }
            var node = findNode(target.dataset.cfNode);
            if(!node) return;
            if(act === 'mode'){
                node.comfyModes = node.comfyModes || {};
                var mode = target.dataset.cfMode;
                if((node.comfyModes[target.dataset.cfId] || 'run') === mode) delete node.comfyModes[target.dataset.cfId];
                else node.comfyModes[target.dataset.cfId] = mode;
                persist();
                repaint();
            } else if(act === 'expand'){
                node.comfyExpanded = node.comfyExpanded || {};
                node.comfyExpanded[target.dataset.cfId] = !node.comfyExpanded[target.dataset.cfId];
                repaint();
            } else if(act === 'rest'){
                node.comfyShowRest = !node.comfyShowRest;
                persist();
                repaint();
            } else if(act === 'run'){
                runFlowNode(node);
            } else if(act === 'cancel'){
                cancelFlowNode(node);
            }
        }, true);

        // 创建菜单新增的「工作流卡片」按钮：在捕获阶段拦截，
        // 避免落入 smart-canvas.js 的大 switch（它不认识这个类型）。
        document.addEventListener('click', function(event){
            var target = event.target.closest ? event.target.closest('[data-create-type="comfy-flow"]') : null;
            if(!target) return;
            event.preventDefault();
            event.stopPropagation();
            openWorkflowPicker();
        }, true);

        function handleParamChange(event){
            var target = event.target;
            if(!target || !target.dataset || !target.dataset.cfParam) return;
            var parts = String(target.dataset.cfParam).split('::');
            if(parts.length < 2) return;
            var nodeId = parts[0];
            var key = parts.slice(1).join('::');
            var host = target.closest ? target.closest('.image-node') : null;
            var node = host ? findNode(host.dataset.id) : null;
            if(!node) return;
            node.comfyOverrides = node.comfyOverrides || {};
            node.comfyOverrides[nodeId] = node.comfyOverrides[nodeId] || {};
            if(target.type === 'checkbox') node.comfyOverrides[nodeId][key] = target.checked;
            else if(target.type === 'number') node.comfyOverrides[nodeId][key] = Number(target.value);
            else node.comfyOverrides[nodeId][key] = target.value;
            persist();
        }
        document.addEventListener('change', handleParamChange, true);
        document.addEventListener('input', function(event){
            if(event.target && event.target.type === 'checkbox') handleParamChange(event);
        }, true);

        // 卡片内的滚动与输入不应该被画布当成拖拽
        document.addEventListener('mousedown', function(event){
            if(event.target && event.target.closest && event.target.closest('.cf-card')){
                event.stopPropagation();
            }
        }, true);
        document.addEventListener('wheel', function(event){
            if(event.target && event.target.closest && event.target.closest('.cf-list')){
                event.stopPropagation();
            }
        }, {capture: true, passive: true});
    }

    // ---------------------------------------------------------------------
    // 接入点
    // ---------------------------------------------------------------------
    function boot(){
        if(CF.booted) return;
        if(typeof window.nodeBodyHtml !== 'function' || typeof window.imageLayout !== 'function') return;
        if(typeof nodes === 'undefined') return;
        CF.booted = true;
        injectStyles();

        var originalBody = window.nodeBodyHtml;
        window.nodeBodyHtml = function(node, layout){
            if(isFlowNode(node)) return cfNodeBodyHtml(node, layout);
            return originalBody(node, layout);
        };

        var originalLayout = window.imageLayout;
        window.imageLayout = function(images, scale, node){
            if(isFlowNode(node)){
                return {
                    cols: 1,
                    rows: 1,
                    width: Math.max(240, Math.round(Number(node.w) || DEFAULT_W)),
                    height: Math.max(200, Math.round(Number(node.h) || DEFAULT_H)),
                    thumb: 96,
                    single: true
                };
            }
            return originalLayout(images, scale, node);
        };

        bindEvents();

        // 资产库面板切到「工作流」tab 时，用工作流卡片列表替换占位文案。
        // renderAssetLibrary 是 smart-canvas.js 的全局函数，包装后所有调用点都会经过这里。
        if(typeof window.renderAssetLibrary === 'function'){
            var originalAssetRender = window.renderAssetLibrary;
            window.renderAssetLibrary = function(){
                var out = originalAssetRender.apply(this, arguments);
                renderWorkflowTab();
                return out;
            };
        }

        window.createComfyFlowNode = createFlowNode;
        window.openComfyFlowPicker = openWorkflowPicker;
        window.__comfyFlow = CF;
    }

    if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
    else boot();
})();
