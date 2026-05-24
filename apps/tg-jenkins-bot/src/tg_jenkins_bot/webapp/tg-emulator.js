(function() {
    // 1. Activation Guard
    const isLocalHost = ['localhost', '127.0.0.1'].includes(location.hostname);
    const hasRealSDK = window.Telegram?.WebApp?.initData;

    if (!isLocalHost || hasRealSDK) {
        // Do nothing in production or inside actual Telegram client
        return;
    }

    // 2. Setup Base Namespaces
    window.Telegram = window.Telegram || {};
    const WebApp = {};
    window.Telegram.WebApp = WebApp;

    // 3. Properties Setup
    WebApp.initData = "preview";
    WebApp.initDataUnsafe = {
        user: {
            id: 12345,
            first_name: "Preview",
            username: "preview_dev"
        }
    };

    // Theme preset definitions
    const lightTheme = {
        bg_color: '#ffffff',
        secondary_bg_color: '#f4f4f7',
        text_color: '#000000',
        hint_color: '#8e8e93',
        link_color: '#007ee5',
        button_color: '#2481cc',
        button_text_color: '#ffffff',
        destructive_text_color: '#ff3b30',
        section_bg_color: '#ffffff',
        section_header_text_color: '#8e8e93',
        subtitle_text_color: '#8e8e93',
        header_bg_color: '#f4f4f7',
        section_separator_color: 'rgba(0, 0, 0, 0.08)',
        bottom_bar_bg_color: '#f4f4f7'
    };

    const darkTheme = {
        bg_color: '#1c242c',
        secondary_bg_color: '#0f171e',
        text_color: '#ffffff',
        hint_color: '#708499',
        link_color: '#5288c1',
        button_color: '#5288c1',
        button_text_color: '#ffffff',
        destructive_text_color: '#ff3b30',
        section_bg_color: '#1c242c',
        section_header_text_color: '#708499',
        subtitle_text_color: '#708499',
        header_bg_color: '#0f171e',
        section_separator_color: 'rgba(255, 255, 255, 0.08)',
        bottom_bar_bg_color: '#0f171e'
    };

    function getThemeParams() {
        const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        return isDark ? darkTheme : lightTheme;
    }

    WebApp.colorScheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    WebApp.themeParams = getThemeParams();

    // 4. Events System
    const events = {};
    WebApp.onEvent = function(eventType, callback) {
        if (!events[eventType]) {
            events[eventType] = [];
        }
        events[eventType].push(callback);
    };

    // Auto-sync dark/light mode
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
        WebApp.colorScheme = e.matches ? 'dark' : 'light';
        WebApp.themeParams = getThemeParams();
        console.log(`🔧 [Emulator] Theme changed dynamically to ${WebApp.colorScheme}`);
        if (events['themeChanged']) {
            events['themeChanged'].forEach(cb => {
                try { cb(); } catch (err) { console.error(err); }
            });
        }
    });

    // 5. Basic Methods
    WebApp.ready = function() {
        console.log("🔧 [Emulator] WebApp.ready() called");
    };

    WebApp.expand = function() {
        console.log("🔧 [Emulator] WebApp.expand() called");
    };

    WebApp.setHeaderColor = function(color) {
        console.log(`🔧 [Emulator] WebApp.setHeaderColor("${color}") called`);
    };

    WebApp.setBackgroundColor = function(color) {
        console.log(`🔧 [Emulator] WebApp.setBackgroundColor("${color}") called`);
    };

    WebApp.openTelegramLink = function(url) {
        console.log(`🔧 [Emulator] WebApp.openTelegramLink("${url}")`);
        window.open(url, '_blank');
    };

    // Vertical swipe control (API 7.7)
    WebApp.disableVerticalSwipes = function() {
        console.log("🔧 [Emulator] WebApp.disableVerticalSwipes() called");
    };

    WebApp.enableVerticalSwipes = function() {
        console.log("🔧 [Emulator] WebApp.enableVerticalSwipes() called");
    };

    // Bottom bar color (API 7.10)
    WebApp.setBottomBarColor = function(color) {
        console.log(`🔧 [Emulator] WebApp.setBottomBarColor("${color}") called`);
    };

    // 6. Native-Style Popup Modal
    WebApp.showPopup = function(params, callback) {
        console.log("🔧 [Emulator] WebApp.showPopup()", params);

        // Clean up any existing popups first
        const existing = document.querySelector('.emu-popup-overlay');
        if (existing) {
            existing.remove();
        }

        const overlay = document.createElement('div');
        overlay.className = 'emu-popup-overlay';

        const card = document.createElement('div');
        card.className = 'emu-popup-card';

        if (params.title) {
            const title = document.createElement('h3');
            title.innerText = params.title;
            card.appendChild(title);
        }

        if (params.message) {
            const message = document.createElement('p');
            message.innerText = params.message;
            card.appendChild(message);
        }

        const btnContainer = document.createElement('div');
        btnContainer.className = 'emu-popup-buttons';

        if (params.buttons && params.buttons.length > 0) {
            params.buttons.forEach(btnSpec => {
                const btn = document.createElement('button');
                btn.className = 'emu-popup-btn';
                if (btnSpec.type === 'destructive') {
                    btn.classList.add('emu-popup-destructive');
                } else if (btnSpec.type === 'cancel') {
                    btn.classList.add('emu-popup-cancel');
                }
                btn.innerText = btnSpec.text || 'OK';
                btn.addEventListener('click', () => {
                    overlay.remove();
                    if (callback) callback(btnSpec.id);
                });
                btnContainer.appendChild(btn);
            });
        } else {
            // Default OK button
            const btn = document.createElement('button');
            btn.className = 'emu-popup-btn';
            btn.innerText = 'OK';
            btn.addEventListener('click', () => {
                overlay.remove();
                if (callback) callback('');
            });
            btnContainer.appendChild(btn);
        }

        card.appendChild(btnContainer);
        overlay.appendChild(card);

        // Click overlay background to dismiss
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) {
                overlay.remove();
                if (callback) callback('');
            }
        });

        document.body.appendChild(overlay);
    };

    // 7. Dynamic MainButton Implementation
    const MainButton = {
        _onClickCb: null,
        _enabled: true,
        _visible: false,
        _text: 'CONTINUE',
        _color: '#2481cc',
        _textColor: '#ffffff',
        _progress: false,

        onClick: function(cb) {
            this._onClickCb = cb;
        },

        show: function() {
            this._visible = true;
            this._updateDOM();
        },

        hide: function() {
            this._visible = false;
            this._updateDOM();
        },

        enable: function() {
            this._enabled = true;
            this._updateDOM();
        },

        disable: function() {
            this._enabled = false;
            this._updateDOM();
        },

        setParams: function(params) {
            if (params.text !== undefined) this._text = params.text;
            if (params.color !== undefined) this._color = params.color;
            if (params.text_color !== undefined) this._textColor = params.text_color;
            if (params.is_active !== undefined) this._enabled = params.is_active;
            if (params.is_visible !== undefined) this._visible = params.is_visible;
            this._updateDOM();
        },

        showProgress: function(leaveActive = false) {
            this._progress = true;
            if (!leaveActive) {
                this._enabled = false;
            }
            this._updateDOM();
        },

        hideProgress: function() {
            this._progress = false;
            this._enabled = true;
            this._updateDOM();
        },

        _updateDOM: function() {
            const btn = document.querySelector('.emu-main-button');
            if (!btn) return;

            btn.style.display = this._visible ? 'flex' : 'none';
            btn.disabled = !this._enabled;
            btn.style.backgroundColor = this._color;
            btn.style.color = this._textColor;

            const textEl = btn.querySelector('.emu-main-button-text');
            const spinnerEl = btn.querySelector('.emu-main-button-spinner');

            if (textEl) textEl.innerText = this._text;
            if (spinnerEl) {
                spinnerEl.style.display = this._progress ? 'inline-flex' : 'none';
            }
        }
    };
    WebApp.MainButton = MainButton;

    // 8. Dynamic BackButton Implementation
    const BackButton = {
        _onClickCb: null,
        _visible: false,

        onClick: function(cb) {
            this._onClickCb = cb;
        },

        show: function() {
            this._visible = true;
            this._updateDOM();
        },

        hide: function() {
            this._visible = false;
            this._updateDOM();
        },

        _updateDOM: function() {
            const btn = document.querySelector('.emu-back-button');
            if (!btn) return;
            btn.style.display = this._visible ? 'flex' : 'none';
        }
    };
    WebApp.BackButton = BackButton;

    // 9. Tactile HapticFeedback Implementation
    const HapticFeedback = {
        selectionChanged: function() {
            console.log('📳 [Haptic] selectionChanged');
            try { navigator.vibrate?.(10); } catch (e) {}
        },
        impactOccurred: function(style) {
            console.log('📳 [Haptic] impactOccurred:', style);
            const duration = style === 'heavy' ? 40 : style === 'medium' ? 25 : 12;
            try { navigator.vibrate?.(duration); } catch (e) {}
        },
        notificationOccurred: function(type) {
            console.log('📳 [Haptic] notificationOccurred:', type);
            const duration = type === 'error' ? 60 : type === 'warning' ? 40 : 20;
            try { navigator.vibrate?.(duration); } catch (e) {}
        }
    };
    WebApp.HapticFeedback = HapticFeedback;

    // 10. Append DOM controls once loaded
    function initDOM() {
        // Emulator badge
        const badge = document.createElement('div');
        badge.className = 'emu-badge';
        badge.innerText = '🔧 EMULATOR';
        document.body.appendChild(badge);

        // MainButton
        const mainBtn = document.createElement('button');
        mainBtn.className = 'emu-main-button';
        mainBtn.style.display = 'none';
        mainBtn.innerHTML = `
            <span class="emu-main-button-text">CONTINUE</span>
            <span class="emu-main-button-spinner" style="display: none; align-items: center; justify-content: center; width: 18px; height: 18px;">
                <svg class="spinner-ios" style="width: 18px; height: 18px; animation-duration:0.65s; color: inherit;" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <circle cx="12" cy="12" r="10" stroke="rgba(255, 255, 255, 0.15)" stroke-width="3"></circle>
                    <path d="M12 2C6.47715 2 2 6.47715 2 12" stroke="currentColor" stroke-width="3" stroke-linecap="round"></path>
                </svg>
            </span>
        `;
        mainBtn.addEventListener('click', () => {
            if (MainButton._onClickCb) {
                MainButton._onClickCb();
            }
        });
        document.body.appendChild(mainBtn);

        // BackButton
        const backBtn = document.createElement('button');
        backBtn.className = 'emu-back-button';
        backBtn.style.display = 'none';
        backBtn.innerHTML = `
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <line x1="19" y1="12" x2="5" y2="12"></line>
                <polyline points="12 19 5 12 12 5"></polyline>
            </svg>
        `;
        backBtn.addEventListener('click', () => {
            if (BackButton._onClickCb) {
                BackButton._onClickCb();
            }
        });
        document.body.appendChild(backBtn);

        // Ensure initially synced visual values
        MainButton._updateDOM();
        BackButton._updateDOM();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initDOM);
    } else {
        initDOM();
    }

    // 11. Colorful Console Header
    console.log(
        '%c🔧 Telegram SDK Emulator Active %c\n' +
        'Running in local development mode. initData="preview"',
        'background: #2481cc; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold;',
        'color: #708499;'
    );
})();
