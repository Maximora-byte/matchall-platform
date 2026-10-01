(function () {
    function currentLanguage() {
        var config = window.MatchAllLive2D || {};
        var htmlLang = (document.documentElement.getAttribute('lang') || '').toLowerCase().replace('_', '-');
        var path = window.location.pathname.toLowerCase();

        if (path.indexOf('/zh-tw/') === 0 || htmlLang.indexOf('zh-tw') === 0) {
            return 'zh-tw';
        }
        if (path.indexOf('/en/') === 0 || htmlLang.indexOf('en') === 0) {
            return 'en';
        }
        if (path.indexOf('/zh-cn/') === 0 || htmlLang.indexOf('zh-cn') === 0 || htmlLang.indexOf('zh-hans') === 0) {
            return 'zh-cn';
        }

        return config.language || 'zh-cn';
    }

    function messages() {
        var config = window.MatchAllLive2D || {};
        var lang = currentLanguage();
        var pack = config.messages || {};
        return pack[lang] || pack['zh-cn'] || {
            greeting: 'Welcome to MatchAll Blog',
            notice: 'Live2D assets are for research and learning only. No commercial use.',
            short_notice: 'Research and learning only. No commercial use.',
            footer_notice: 'Live2D assets are for research and learning only. No commercial use.',
            touch: ['Less poking, more building.'],
            skin: ['Switch character', 'New character online.']
        };
    }

    function renderNotice() {
        var text = messages();
        var note = document.querySelector('.matchall-live2d-note span');
        if (note && text.notice) {
            note.textContent = text.short_notice || text.notice;
        }

        document.querySelectorAll('#footer div').forEach(function (node) {
            if (/Live2D/.test(node.textContent || '')) {
                node.textContent = text.footer_notice || text.notice;
            }
        });

        if (window.MatchAllLive2D) {
            window.MatchAllLive2D.language = currentLanguage();
        }
    }

    function pick(list, fallback) {
        if (!Array.isArray(list) || list.length === 0) {
            return fallback;
        }
        return list[Math.floor(Math.random() * list.length)];
    }

    function onModelLoad(model) {
        var text = messages();
        var container = document.getElementById('pio-container');
        var canvas = document.getElementById('pio');
        var motionManager = model && model.internalModel && model.internalModel.motionManager;

        if (container && model && model.internalModel && model.internalModel.settings) {
            container.dataset.model = model.internalModel.settings.name || 'Live2D';
        }

        if (!canvas || !motionManager || !window.pio_reference) {
            return;
        }

        canvas.onclick = function () {
            if (motionManager.state && motionManager.state.currentGroup !== 'Idle') {
                return;
            }
            window.pio_reference.modules.render(pick(text.touch, text.greeting));
            if (window.pio_reference.model && typeof window.pio_reference.model.motion === 'function') {
                window.pio_reference.model.motion('Idle');
            }
        };
    }

    function boot() {
        var config = window.MatchAllLive2D || {};
        var text = messages();

        if (!window.Paul_Pio || !window.PIXI || !window.PIXI.live2d || !Array.isArray(config.models)) {
            return;
        }

        renderNotice();

        try {
            pio_alignment = 'right';
        } catch (error) {
            window.pio_alignment = 'right';
        }
        window.pio_reference = new window.Paul_Pio({
            mode: 'fixed',
            hidden: false,
            content: {
                link: '/',
                welcome: [text.greeting],
                touch: pick(text.touch, text.greeting),
                skin: text.skin || ['Switch character', 'New character online.'],
                custom: [
                    { selector: '.post-title a, .article-title a, .list .postname', type: 'read' },
                    { selector: '.post-content a, .page-content a, .post a', type: 'link' },
                    { selector: '.comment-form', text: pick(text.touch, text.greeting) }
                ]
            },
            night: '',
            model: config.models,
            tips: true,
            onModelLoad: onModelLoad
        });

        if (typeof window.pio_refresh_style === 'function') {
            window.pio_refresh_style();
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        window.setTimeout(boot, 0);
    }

    window.addEventListener('pageshow', renderNotice);
    document.addEventListener('pjax:complete', renderNotice);
    document.addEventListener('pjax:end', renderNotice);
})();
