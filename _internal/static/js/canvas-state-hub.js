/** Read-only state snapshot hub for the canvas (B1 / L1, behavior-neutral registry). */
(function(global){
    'use strict';

    // 注入表：主文件在状态声明之后 configure 一次；每个 key 是一个指向真变量的 getter 闭包。
    // 只读（get/keys/snapshot），不设写口——写仍走主文件原路径，避免 L1 阶段引入双写源。
    const accessors = {};

    function configure(options){
        Object.assign(accessors, options || {});
    }

    function get(key){
        const fn = accessors[key];
        return typeof fn === 'function' ? fn() : undefined;
    }

    function has(key){ return typeof accessors[key] === 'function'; }

    function keys(){ return Object.keys(accessors); }

    // 一次取全部（调试/自省用；顺序稳定=注册顺序）
    function snapshot(){
        const out = {};
        Object.keys(accessors).forEach(function(k){ out[k] = accessors[k](); });
        return out;
    }

    global.CanvasStateHub = { configure, get, has, keys, snapshot };
})(typeof window !== 'undefined' ? window : this);
