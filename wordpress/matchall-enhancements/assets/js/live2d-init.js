(function () {
    function getMessages() {
        var config = window.MatchAllLive2D || {};
        var lang = config.language || 'zh-cn';
        var messages = config.messages || {};
        return messages[lang] || messages['zh-cn'] || {
            greeting: 'Welcome to MatchAll Blog',
            notice: 'Research and learning only. No commercial use.'
        };
    }

    function ensureBubble() {
        var existing = document.querySelector('.matchall-live2d-bubble');
        if (existing) {
            return existing;
        }

        var bubble = document.createElement('div');
        bubble.className = 'matchall-live2d-bubble';
        bubble.setAttribute('aria-live', 'polite');
        document.body.appendChild(bubble);
        return bubble;
    }

    function showBubble() {
        var messages = getMessages();
        var bubble = ensureBubble();
        bubble.innerHTML = '<strong>' + messages.greeting + '</strong><span>' + messages.notice + '</span>';
        bubble.classList.add('is-visible');

        window.setTimeout(function () {
            bubble.classList.remove('is-visible');
        }, 7600);
    }

    function bootLive2D() {
        if (!window.L2Dwidget || !window.MatchAllLive2D || !window.MatchAllLive2D.modelJson) {
            return;
        }

        window.L2Dwidget.init({
            model: {
                jsonPath: window.MatchAllLive2D.modelJson,
                scale: 1
            },
            display: {
                position: 'right',
                width: 170,
                height: 320,
                hOffset: 12,
                vOffset: -18
            },
            mobile: {
                show: false
            },
            react: {
                opacityDefault: 0.86,
                opacityOnHover: 1
            },
            dialog: {
                enable: false
            }
        });

        window.setTimeout(showBubble, 1200);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bootLive2D);
    } else {
        bootLive2D();
    }
})();
