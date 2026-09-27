/* Runs cascade rounds with bounded concurrency and waits for active work on failure. */
(function(global){
    'use strict';

    const deps = {};
    function configure(options){Object.assign(deps, options || {});}

    async function runWithLimit(roundIndexes, limit, runner, runState=null){
        let next = 0;
        let stopped = false;
        let failure = null;
        const workerCount = Math.max(1, Math.min(Number(limit) || 1, roundIndexes.length));
        const workers = Array.from({length:workerCount}, async () => {
            while(next < roundIndexes.length){
                if(stopped || deps.shouldStop(runState)) break;
                const roundOffset = next++;
                const current = roundIndexes[roundOffset];
                try {
                    await runner(current, roundOffset);
                } catch(error) {
                    stopped = true;
                    if(!deps.isStoppedError(error) && !failure) failure = error;
                    break;
                }
            }
        });
        await Promise.all(workers);
        if(failure) throw failure;
    }

    global.CanvasCascadeRoundScheduler = {configure, runWithLimit};
})(typeof window !== 'undefined' ? window : globalThis);
