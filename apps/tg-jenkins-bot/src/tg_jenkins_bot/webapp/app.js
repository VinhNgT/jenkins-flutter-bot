/**
 * Telegram Web App — Modular Native Visual Controller
 */

// Application State
let config = null;
let selectedBranch = null;
let isTelegram = false;
let initData = 'preview';
let eventSource = null;
let relativeTimeInterval = null;

// DOM Elements cache
const mainScreen = document.getElementById('mainScreen');
const errorScreen = document.getElementById('errorScreen');
const loadingScreen = document.getElementById('loadingScreen');

const errorTitle = document.getElementById('errorTitle');
const errorDescription = document.getElementById('errorDescription');
const errorActionContainer = document.getElementById('errorActionContainer');

const appNameTitle = document.getElementById('appName');
const branchesContainer = document.getElementById('branchesContainer');
const customBranchInput = document.getElementById('customBranchInput');
const customBranchRow = document.getElementById('customBranchRow');
const customInputClear = document.getElementById('customInputClear');
const buildsList = document.getElementById('buildsList');
const buildsCountBadge = document.getElementById('buildsCountBadge');
const fallbackBtnContainer = document.getElementById('fallbackBtnContainer');
const fallbackTriggerBtn = document.getElementById('fallbackTriggerBtn');

// Toast Notification element
let toastTimeout = null;
const toastEl = document.getElementById('toastNotification');
const toastText = document.getElementById('toastText');

// Initialize Web App Context
function initContext() {
    const tg = window.Telegram ? window.Telegram.WebApp : null;
    
    if (tg && tg.initData) {
        isTelegram = true;
        initData = tg.initData;
        
        // Expand app to fill viewport natively
        tg.ready();
        tg.expand();
        
        // Prevent accidental close by vertical swipe on scrollable content.
        // Users can still minimize/close via the swipe down gesture on the header.
        if (tg.disableVerticalSwipes) {
            tg.disableVerticalSwipes();
        }
        
        // Synchronize themes and header styling
        syncThemeColors();
        tg.onEvent('themeChanged', syncThemeColors);

        // Set bottom bar color to match theme (API 7.10 — area behind MainButton)
        if (tg.setBottomBarColor) {
            tg.setBottomBarColor('secondary_bg_color');
        }
        
        // Setup WebApp BackButton (initially hidden, used in error fallback screens)
        tg.BackButton.onClick(handleBackButtonClick);
        
        // Setup Native MainButton parameters
        tg.MainButton.onClick(handleTriggerClick);
        updateMainButtonState(false);
        
        // Hide browser fallback triggers inside Telegram client
        if (fallbackBtnContainer) {
            fallbackBtnContainer.style.display = 'none';
        }
    } else {
        // Enforce Telegram client constraints
        document.addEventListener('DOMContentLoaded', () => {
            showErrorState("Telegram Client Required", "This application can only be accessed securely inside the official Telegram client messenger.", { error: "direct_browser_disabled" });
        });
        throw new Error("Telegram Client Required: Direct browser authentication disabled.");
    }
}

// Map Telegram colors and toggle theme classes dynamically
function syncThemeColors() {
    const tg = window.Telegram ? window.Telegram.WebApp : null;
    if (!tg) return;
    
    const theme = tg.themeParams;
    const isDark = tg.colorScheme === 'dark';
    const root = document.documentElement;
    
    // Toggle system visual mode classes
    if (isDark) {
        document.body.classList.add('tg-dark');
        document.body.classList.remove('tg-light');
    } else {
        document.body.classList.add('tg-light');
        document.body.classList.remove('tg-dark');
    }
    document.body.classList.add('tg-theme-loaded');
    // CSS selector :root:not(.tg-theme-loaded) targets <html>, not <body>
    document.documentElement.classList.add('tg-theme-loaded');
    
    // Inject CSS variables matching Telegram visual settings
    if (theme.bg_color) root.style.setProperty('--tg-color-bg', theme.bg_color);
    if (theme.secondary_bg_color) root.style.setProperty('--tg-color-secondary-bg', theme.secondary_bg_color);
    if (theme.text_color) root.style.setProperty('--tg-color-text', theme.text_color);
    if (theme.hint_color) root.style.setProperty('--tg-color-hint', theme.hint_color);
    if (theme.link_color) root.style.setProperty('--tg-color-link', theme.link_color);
    if (theme.button_color) root.style.setProperty('--tg-color-button', theme.button_color);
    if (theme.button_text_color) root.style.setProperty('--tg-color-button-text', theme.button_text_color);
    if (theme.destructive_text_color) root.style.setProperty('--tg-color-destructive', theme.destructive_text_color);
    
    // Set modern nested elements support
    root.style.setProperty('--tg-color-section-bg', theme.section_bg_color || theme.bg_color || (isDark ? '#1c242c' : '#ffffff'));
    root.style.setProperty('--tg-color-section-header', theme.section_header_text_color || theme.hint_color || (isDark ? '#708499' : '#8e8e93'));
    root.style.setProperty('--tg-color-subtitle', theme.subtitle_text_color || theme.hint_color || (isDark ? '#708499' : '#8e8e93'));
    root.style.setProperty('--tg-color-header-bg', theme.header_bg_color || theme.secondary_bg_color || (isDark ? '#0f171e' : '#f4f4f7'));
    
    // Set section separator and divider (API 7.6: section_separator_color)
    const separatorColor = theme.section_separator_color || (isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.08)');
    root.style.setProperty('--tg-color-separator', separatorColor);
    root.style.setProperty('--tg-color-divider', separatorColor);
    
    // Update native Telegram header colors
    tg.setHeaderColor('secondary_bg_color');
    tg.setBackgroundColor('secondary_bg_color');
}

// Fetch main configuration schema
async function fetchConfig() {
    try {
        const response = await fetch('/api/webapp/config', {
            headers: {
                'X-Telegram-Init-Data': initData
            }
        });

        if (response.status === 403 || response.status === 401) {
            const data = await response.json();
            let desc = "This chat is not authorized to trigger builds.";
            let detail = null;
            if (data.detail) {
                if (typeof data.detail === 'object') {
                    desc = data.detail.message || desc;
                    detail = data.detail;
                } else {
                    desc = data.detail;
                }
            }
            showErrorState("Access Denied", desc, detail);
            return;
        }

        if (!response.ok) {
            throw new Error(`Server responded with HTTP ${response.status}`);
        }

        config = await response.json();
        renderMainView();
        startSSEStream();
    } catch (err) {
        console.error(err);
        showErrorState("Service Offline", "The build orchestration controller is currently offline or unreachable. Please try again shortly.", { error: "service_offline" });
    }
}

// Render Core Application View
function renderMainView() {
    // Render dynamic configuration details
    if (appNameTitle) appNameTitle.innerText = config.app_name;
    
    // Construct pre-configured branches list
    if (branchesContainer) {
        branchesContainer.innerHTML = '';
        config.branches.forEach((branch, index) => {
            const row = document.createElement('div');
            row.className = 'tg-list-item';
            row.dataset.ref = branch.ref;
            row.innerHTML = `
                <div class="tg-list-item-content">
                    <span class="tg-list-item-title">${branch.label}</span>
                    <span class="tg-list-item-subtitle">${branch.ref}</span>
                </div>
                <div class="tg-radio-icon">
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <path d="M16.6666 5L7.49992 14.1667L3.33325 10" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                </div>
            `;
            
            row.addEventListener('click', () => {
                selectBranch(branch.ref, row);
            });
            branchesContainer.appendChild(row);
        });
    }
    
    // Clear and display
    resetInputState();
    renderActiveBuilds();
    setupRelativeTicker();
    
    // Hide error / loading screen overlays cleanly
    if (loadingScreen) loadingScreen.style.display = 'none';
    if (errorScreen) errorScreen.classList.remove('active');
    if (mainScreen) mainScreen.style.display = 'flex';
    
    // Ensure native back button is hidden on home screen
    if (isTelegram) {
        window.Telegram.WebApp.BackButton.hide();
    }
}

// Render active builds panel
function renderActiveBuilds() {
    if (!buildsList) return;
    
    buildsList.innerHTML = '';
    const builds = config.active_builds || [];
    
    // Update badge count
    if (buildsCountBadge) {
        if (builds.length > 0) {
            buildsCountBadge.innerText = builds.length;
            buildsCountBadge.style.display = 'inline-flex';
        } else {
            buildsCountBadge.style.display = 'none';
        }
    }
    
    if (builds.length === 0) {
        buildsList.innerHTML = `
            <div class="tg-empty-row">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect>
                    <line x1="8" y1="21" x2="16" y2="21"></line>
                    <line x1="12" y1="17" x2="12" y2="21"></line>
                </svg>
                <span>No active build streams running.</span>
            </div>
        `;
        return;
    }
    
    const currentUserId = getTelegramUserId();
    
    builds.forEach(build => {
        const row = document.createElement('div');
        row.className = 'tg-list-item';
        row.style.cursor = 'default'; // Static display row
        row.dataset.timestamp = build.triggered_at;
        
        // Check user credentials: Only display cancel trigger if logged-in user is creator
        // In preview mode (initData === 'preview'), we permit cancellation globally for testing.
        const canCancel = (initData === 'preview') || (currentUserId && build.triggered_by_id === currentUserId);
        
        let cancelControl = '';
        if (canCancel) {
            cancelControl = `
                <button class="tg-cancel-action" data-request-id="${build.request_id}">
                    <span>🚫 Cancel</span>
                </button>
            `;
        } else {
            // Read-only indicator showing who triggered it
            cancelControl = `
                <span style="font-size: 13px; color: var(--tg-color-hint); font-style: italic;">Locked</span>
            `;
        }
        
        row.innerHTML = `
            <div style="display: flex; align-items: center; gap: 10px; flex-grow: 1;">
                <svg class="spinner-ios" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <circle cx="12" cy="12" r="10" stroke="var(--tg-color-divider)" stroke-width="2.5"></circle>
                    <path d="M12 2C6.47715 2 2 6.47715 2 12" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"></path>
                </svg>
                <div class="tg-list-item-content">
                    <span class="tg-list-item-title">${build.label}</span>
                    <span class="tg-list-item-subtitle" style="display: flex; align-items: center;">
                        <span class="pulsing-dot"></span>
                        by ${build.triggered_by} · <span class="relative-time-ticker">just now</span>
                    </span>
                </div>
            </div>
            <div class="tg-list-item-right" style="flex-shrink: 0; padding-left: 8px;">
                ${cancelControl}
            </div>
        `;
        
        // Attach interactive cancellation listener
        const cancelBtn = row.querySelector('.tg-cancel-action');
        if (cancelBtn) {
            cancelBtn.addEventListener('click', () => {
                promptBuildCancellation(build, cancelBtn);
            });
        }
        
        buildsList.appendChild(row);
    });
    
    // Run immediate relative evaluation
    evaluateRelativeTimes();
}

// Select a preconfigured branch row
function selectBranch(branchRef, element) {
    hapticTapSelection();
    
    // Clear custom input and clear class states
    if (customBranchInput) customBranchInput.value = '';
    if (customBranchRow) {
        customBranchRow.classList.remove('selected', 'populated');
    }
    
    // Remove active select classes
    document.querySelectorAll('.tg-list-item').forEach(item => {
        item.classList.remove('selected');
    });
    
    // Set target row active
    element.classList.add('selected');
    selectedBranch = branchRef;
    
    validateTriggerState();
}

// Clear all active selection fields
function resetInputState() {
    selectedBranch = null;
    if (customBranchInput) customBranchInput.value = '';
    if (customBranchRow) {
        customBranchRow.classList.remove('selected', 'populated');
    }
    document.querySelectorAll('.tg-list-item').forEach(item => {
        item.classList.remove('selected');
    });
    validateTriggerState();
}

// Validate Selection state and toggle buttons
function validateTriggerState() {
    const isDuplicate = (config && config.active_builds || []).some(b => b.ref === selectedBranch);
    let enabled = selectedBranch !== null && selectedBranch.trim() !== '';
    
    if (isDuplicate && enabled) {
        showToast(`A build on '${selectedBranch}' is already running. Please wait or cancel it first.`, 'error');
        enabled = false;
    }
    
    updateMainButtonState(enabled);
}

// Toggle native/fallback main button controls
function updateMainButtonState(enabled) {
    if (isTelegram) {
        const tg = window.Telegram.WebApp;
        if (enabled) {
            tg.MainButton.setParams({
                text: 'TRIGGER BUILD',
                color: tg.themeParams.button_color || '#2481cc',
                text_color: tg.themeParams.button_text_color || '#ffffff',
                is_active: true,
                is_visible: true
            });
        } else {
            tg.MainButton.hide();
        }
    } else {
        if (fallbackTriggerBtn) {
            fallbackTriggerBtn.disabled = !enabled;
        }
    }
}

// Action: Trigger Build
async function handleTriggerClick() {
    if (!selectedBranch) return;
    
    hapticImpact('medium');
    setLoadingState(true);
    
    try {
        const response = await fetch('/api/webapp/trigger', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Telegram-Init-Data': initData
            },
            body: JSON.stringify({ branch: selectedBranch })
        });
        
        const resData = await response.json();
        if (!response.ok) {
            throw new Error(resData.detail || "Build trigger failed");
        }
        
        // Reset selections
        resetInputState();
        
        // Trigger Success feedback
        hapticNotification('success');
        showToast("Build successfully triggered!");
        
        // Soft refresh configuration
        await fetchConfig();
    } catch (err) {
        console.error(err);
        hapticNotification('error');
        showToast(err.message || "Failed to trigger build. Please retry.", "error");
    } finally {
        setLoadingState(false);
    }
}

// Action: Cancel Build Popup Prompt
function promptBuildCancellation(build, buttonEl) {
    hapticImpact('medium');
    
    if (isTelegram) {
        // Utilize the latest highly-premium Telegram sheet Popup API
        window.Telegram.WebApp.showPopup({
            title: 'Cancel Active Build',
            message: `Are you sure you want to stop the build running on branch '${build.ref}'? This action cannot be undone.`,
            buttons: [
                { id: 'cancel_build', type: 'destructive', text: 'Yes, Stop Build' },
                { id: 'dismiss', type: 'cancel', text: 'Keep Running' }
            ]
        }, async (buttonId) => {
            if (buttonId === 'cancel_build') {
                hapticImpact('heavy');
                await cancelBuild(build.request_id, buttonEl);
            }
        });
    } else {
        // Simple fallback alert for browser frames
        if (confirm(`Are you sure you want to stop the build running on branch '${build.ref}'?`)) {
            cancelBuild(build.request_id, buttonEl);
        }
    }
}

// Action: Cancel Build API Operation
async function cancelBuild(requestId, buttonEl) {
    // Visual spinner toggle on target item button
    buttonEl.disabled = true;
    buttonEl.innerHTML = `
        <svg class="spinner-ios" style="width:12px; height:12px; animation-duration:0.6s;" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <circle cx="12" cy="12" r="10" stroke="rgba(255,59,48,0.15)" stroke-width="3"></circle>
            <path d="M12 2C6.47715 2 2 6.47715 2 12" stroke="currentColor" stroke-width="3" stroke-linecap="round"></path>
        </svg>
    `;
    
    try {
        const response = await fetch('/api/webapp/cancel', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Telegram-Init-Data': initData
            },
            body: JSON.stringify({ request_id: requestId })
        });
        
        const resData = await response.json();
        if (!response.ok) {
            throw new Error(resData.detail || "Cancellation failed");
        }
        
        hapticNotification('success');
        showToast("Build successfully cancelled.");
        
        // Soft refresh configuration
        await fetchConfig();
    } catch (err) {
        console.error(err);
        hapticNotification('error');
        showToast(err.message || "Failed to cancel build.", "error");
        
        // Restore cancel button representation
        buttonEl.disabled = false;
        buttonEl.innerHTML = '<span>🚫 Cancel</span>';
    }
}

// Toggle loading controls
function setLoadingState(isLoading) {
    if (isTelegram) {
        const tg = window.Telegram.WebApp;
        if (isLoading) {
            tg.MainButton.showProgress(false);
            tg.MainButton.disable();
        } else {
            tg.MainButton.hideProgress();
            tg.MainButton.enable();
        }
    } else {
        if (fallbackTriggerBtn) {
            fallbackTriggerBtn.disabled = isLoading;
            fallbackTriggerBtn.innerHTML = isLoading ? `
                <svg class="spinner-ios" style="color:var(--tg-color-button-text)" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <circle cx="12" cy="12" r="10" stroke="rgba(255,255,255,0.15)" stroke-width="3"></circle>
                    <path d="M12 2C6.47715 2 2 6.47715 2 12" stroke="currentColor" stroke-width="3" stroke-linecap="round"></path>
                </svg>
            ` : '<span>Trigger Build</span>';
        }
    }
}

// Open / register SSE updates stream
function startSSEStream() {
    if (eventSource) {
        eventSource.close();
    }
    
    const sseUrl = `/api/webapp/stream?init_data=${encodeURIComponent(initData)}`;
    eventSource = new EventSource(sseUrl);
    
    eventSource.addEventListener('builds', (event) => {
        try {
            const activeBuilds = JSON.parse(event.data);
            
            // Compare structure changes to prevent redundant render operations
            if (JSON.stringify(config.active_builds) !== JSON.stringify(activeBuilds)) {
                config.active_builds = activeBuilds;
                renderActiveBuilds();
                validateTriggerState();
            }
        } catch (err) {
            console.error("Failed parsing SSE payload:", err);
        }
    });
    
    eventSource.onerror = (err) => {
        console.warn("EventSource disconnected. Retrying natively...", err);
    };
}

// Close active stream connections
function stopSSEStream() {
    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }
}

// Render Native Error/Access Block views
function showErrorState(title, description, detail = null) {
    stopSSEStream();
    clearRelativeTicker();
    
    if (errorTitle) errorTitle.innerText = title;
    if (errorDescription) errorDescription.innerText = description;
    
    // Clear old actions
    if (errorActionContainer) {
        errorActionContainer.innerHTML = '';
        
        if (detail && detail.error === 'private_chat_disabled' && detail.bot_username) {
            // Render custom invite CTA button
            const btn = document.createElement('button');
            btn.className = 'tg-primary-button';
            btn.innerHTML = `
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="12" y1="5" x2="12" y2="19"></line>
                    <line x1="5" y1="12" x2="19" y2="12"></line>
                </svg>
                <span>Add Bot to Group</span>
            `;
            btn.onclick = () => {
                hapticImpact('medium');
                window.Telegram.WebApp.openTelegramLink(`https://t.me/${detail.bot_username}?startgroup=auth`);
            };
            errorActionContainer.appendChild(btn);
        } else if (detail && detail.error === 'group_not_authorized' && detail.chat_id) {
            // Build copying panel
            const panel = document.createElement('div');
            panel.className = 'tg-action-card';
            panel.innerHTML = `
                <div style="font-size: 11px; color: var(--tg-color-subtitle); font-weight: 700; text-align: left; text-transform: uppercase; letter-spacing:0.5px;">YOUR CHAT ID:</div>
                <div class="tg-copy-container">
                    <input type="text" readonly value="${detail.chat_id}" class="tg-copy-field" id="chatIdField">
                    <button class="tg-copy-button" id="copyIdBtn">📋</button>
                </div>
                <p style="font-size: 12px; color: var(--tg-color-hint); line-height: 1.45; text-align: center; margin-top: 6px;">Share this ID with your system administrator to secure authorized access.</p>
            `;
            errorActionContainer.appendChild(panel);
            
            const field = document.getElementById('chatIdField');
            if (field) {
                field.addEventListener('click', () => field.select());
            }
            
            const copyBtn = document.getElementById('copyIdBtn');
            if (copyBtn) {
                copyBtn.onclick = () => {
                    hapticImpact('light');
                    navigator.clipboard.writeText(String(detail.chat_id))
                        .then(() => {
                            copyBtn.innerText = '✅';
                            showToast("Chat ID copied successfully.");
                            setTimeout(() => { copyBtn.innerText = '📋'; }, 2000);
                        })
                        .catch(e => console.error(e));
                };
            }
        }
    }
    
    // Display the panel and activate BackButton for simple native retries
    if (loadingScreen) loadingScreen.style.display = 'none';
    if (mainScreen) mainScreen.style.display = 'none';
    if (errorScreen) errorScreen.classList.add('active');
    
    if (isTelegram) {
        window.Telegram.WebApp.BackButton.show();
    }
}

// Telegram Header BackButton Event
function handleBackButtonClick() {
    hapticImpact('light');
    if (loadingScreen) loadingScreen.style.display = 'flex';
    if (errorScreen) errorScreen.classList.remove('active');
    if (isTelegram) {
        window.Telegram.WebApp.BackButton.hide();
    }
    fetchConfig();
}

// Trigger sliding native-style toasts
function showToast(message, type = 'success') {
    if (!toastEl) return;
    
    // Cancel prior dismiss timeouts
    if (toastTimeout) {
        clearTimeout(toastTimeout);
    }
    
    if (toastText) toastText.innerText = message;
    
    // Configure visual layouts
    if (type === 'error') {
        toastEl.classList.add('toast-error');
    } else {
        toastEl.classList.remove('toast-error');
    }
    
    // Animate banner view
    toastEl.classList.add('active');
    
    toastTimeout = setTimeout(() => {
        toastEl.classList.remove('active');
    }, 4000);
}

// Extract active client Telegram ID (used for scoped cancellations)
function getTelegramUserId() {
    const tg = window.Telegram ? window.Telegram.WebApp : null;
    if (tg && tg.initDataUnsafe && tg.initDataUnsafe.user) {
        return tg.initDataUnsafe.user.id;
    }
    return null;
}

// Relative active time evaluation engine
function setupRelativeTicker() {
    clearRelativeTicker();
    relativeTimeInterval = setInterval(evaluateRelativeTimes, 2000);
}

function clearRelativeTicker() {
    if (relativeTimeInterval) {
        clearInterval(relativeTimeInterval);
        relativeTimeInterval = null;
    }
}

function evaluateRelativeTimes() {
    document.querySelectorAll('.tg-list-item[data-timestamp]').forEach(row => {
        const timestamp = parseFloat(row.dataset.timestamp);
        const ticker = row.querySelector('.relative-time-ticker');
        if (ticker && !isNaN(timestamp)) {
            const diffSec = Math.floor(Date.now() / 1000 - timestamp);
            if (diffSec < 60) {
                ticker.innerText = 'just now';
            } else {
                ticker.innerText = `${Math.floor(diffSec / 60)}m ago`;
            }
        }
    });
}

// Safe Tactile Haptics Controllers
function hapticTapSelection() {
    try {
        if (isTelegram && window.Telegram.WebApp.HapticFeedback) {
            window.Telegram.WebApp.HapticFeedback.selectionChanged();
        }
    } catch (e) { console.warn(e); }
}

function hapticImpact(style = 'light') {
    try {
        if (isTelegram && window.Telegram.WebApp.HapticFeedback) {
            window.Telegram.WebApp.HapticFeedback.impactOccurred(style);
        }
    } catch (e) { console.warn(e); }
}

function hapticNotification(type = 'success') {
    try {
        if (isTelegram && window.Telegram.WebApp.HapticFeedback) {
            window.Telegram.WebApp.HapticFeedback.notificationOccurred(type);
        }
    } catch (e) { console.warn(e); }
}

// Setup input listeners on static load
function setupInputListeners() {
    if (customBranchInput) {
        customBranchInput.addEventListener('input', (e) => {
            const val = e.target.value;
            
            if (val.trim() !== '') {
                // Populate class toggles for the clear buttons
                if (customBranchRow) {
                    customBranchRow.classList.add('populated', 'selected');
                }
                
                // Deselect preconfigured row representations
                document.querySelectorAll('.tg-list-item:not(#customBranchRow)').forEach(item => {
                    item.classList.remove('selected');
                });
                
                selectedBranch = val.trim();
                validateTriggerState();
                hapticTapSelection();
            } else {
                if (customBranchRow) {
                    customBranchRow.classList.remove('populated', 'selected');
                }
                selectedBranch = null;
                validateTriggerState();
            }
        });
        
        customBranchInput.addEventListener('focus', () => {
            hapticTapSelection();
        });
    }
    
    if (customInputClear) {
        customInputClear.addEventListener('click', () => {
            hapticImpact('light');
            resetInputState();
            if (customBranchInput) customBranchInput.focus();
        });
    }
    
    if (fallbackTriggerBtn) {
        fallbackTriggerBtn.addEventListener('click', handleTriggerClick);
    }
}

// Bootstrap Initialization entry points
document.addEventListener('DOMContentLoaded', () => {
    initContext();
    setupInputListeners();
    fetchConfig();
});
