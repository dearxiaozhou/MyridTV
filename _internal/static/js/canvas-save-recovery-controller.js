/* Owns the bounded retry lifecycle for failed canvas saves. */
(function (global) {
    'use strict';

    function create(options) {
        options = options || {};
        var delays = Array.isArray(options.retryDelays) ? options.retryDelays.slice() : [1000, 3000, 8000];
        var timer = null;
        var retryCount = 0;
        var failureNotified = false;
        var retriesExhaustedNotified = false;

        function clearTimer() {
            if (timer !== null) global.clearTimeout(timer);
            timer = null;
        }

        function reset() {
            clearTimer();
            retryCount = 0;
            failureNotified = false;
            retriesExhaustedNotified = false;
        }

        function fail(config) {
            config = config || {};
            if (!failureNotified) {
                failureNotified = true;
                if (typeof config.onFirstFailure === 'function') config.onFirstFailure();
            }
            var delay = delays[retryCount];
            if (Number.isFinite(delay)) {
                retryCount += 1;
                clearTimer();
                timer = global.setTimeout(function () {
                    timer = null;
                    if (typeof config.retry === 'function') config.retry();
                }, delay);
            } else if (!retriesExhaustedNotified) {
                retriesExhaustedNotified = true;
                if (typeof config.onExhausted === 'function') config.onExhausted();
            }
        }

        function prepareOnlineRetry() {
            if (!failureNotified || timer !== null) return false;
            retryCount = 0;
            failureNotified = false;
            retriesExhaustedNotified = false;
            return true;
        }

        return { reset: reset, fail: fail, prepareOnlineRetry: prepareOnlineRetry };
    }

    global.CanvasSaveRecoveryController = { create: create };
})(window);
