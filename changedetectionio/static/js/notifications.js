// The template library is a copy-on-select editor helper. Applying a template
// never saves Watch/Tag/Global settings; users still click the page's Save.
function setupNotificationTemplateLibrary() {
    var $select = $('#notification-template-select');
    if (!$select.length) return;
    var templates = [];
    var endpoint = $('.notification-template-library').attr('data-list-url');
    var previewEndpoint = $('.notification-template-library').attr('data-preview-url');
    var csrf = $('input[name="csrf_token"]').first().val();
    var headers = csrf ? {'X-CSRFToken': csrf} : {};
    var $title = $('input.notification-title');
    var $body = $('textarea.notification-body');
    var $format = $('select.notification-format');
    var richInternalTitle = '{{ watch_title }}';
    // Rich messages render their own heading from the JSON body. Keep the
    // underlying title input enabled and populated for ordinary formats and
    // existing form validation; never discard it when hiding the field.
    function syncRichTitleVisibility() {
        $('#notification-title-field').toggle($format.val() !== 'telegram_rich');
    }
    $format.on('change', syncRichTitleVisibility);
    syncRichTitleVisibility();
    var $message = $('#notification-template-message');
    var $result = $('#notification-template-preview-result');
    var watchMatch = (typeof notification_base_url === 'string' ? notification_base_url : '').match(/\/notification\/send-test\/([^/?]+)/);
    function say(value) { $message.text(value || ''); }
    function selected() { return templates.find(function(t) { return t.id === $select.val(); }); }
    function current() {
        var format = $format.val() || 'text';
        return {title: format === 'telegram_rich' ? richInternalTitle : ($title.val() || ''),
                body: $body.val() || '', format: format};
    }
    function refresh(items, selectId) {
        templates = items || [];
        $select.empty().append($('<option>').val('').text('Choose a preset or saved template...'));
        templates.forEach(function(t) {
            $select.append($('<option>').val(t.id).text((t.builtin ? 'Preset: ' : 'My template: ') + t.name));
        });
        $select.val(selectId || '');
        updateButtons();
    }
    function updateButtons() {
        var item = selected(), editable = !!(item && !item.builtin);
        $('#notification-template-update, #notification-template-delete').prop('disabled', !editable);
        $('#notification-template-apply').prop('disabled', !item);
    }
    function reload() {
        $.getJSON(endpoint).done(function(data) { refresh(data.templates, $select.val()); })
            .fail(function() { say('Could not load notification templates.'); });
    }
    function mutate(action, item) {
        return $.ajax({url:endpoint, type:'POST', contentType:'application/json', headers:headers,
            data:JSON.stringify({action:action,template:item})}).done(function(data) {
                refresh(data.templates, data.template ? data.template.id : '');
                say(action === 'delete' ? 'Template deleted.' : 'Template saved.');
            }).fail(function(xhr) {
                say((xhr.responseJSON && xhr.responseJSON.error) || 'Template operation failed.');
            });
    }
    $select.on('change', updateButtons);
    $('#notification-template-apply').on('click', function() {
        var item = selected(); if (!item) return;
        var edited = current();
        if ((edited.title.trim() || edited.body.trim()) &&
            (edited.title !== item.title || edited.body !== item.body || edited.format !== item.format) &&
            !window.confirm('Replace the current unsaved notification title, body and format?')) return;
        $title.val(item.format === 'telegram_rich' ? richInternalTitle : item.title).trigger('change');
        $body.val(item.body).trigger('change');
        $format.val(item.format).trigger('change');
        if (item.format === 'telegram_rich') say('Rich Message templates require Telegram tgram:// destinations.');
        $result.hide();
        say('Copied title, body and format to editor. Click the page Save button to apply.');
    });
    $('#notification-template-save').on('click', function() {
        var name = window.prompt('New template name:'); if (!name || !name.trim()) return;
        mutate('create', Object.assign({name:name.trim()},current()));
    });
    $('#notification-template-update').on('click', function() {
        var item=selected(); if (!item || item.builtin) return;
        var name=window.prompt('Template name:',item.name); if (!name || !name.trim()) return;
        if (!window.confirm('Update this saved template? Already configured watches will not change.')) return;
        mutate('update',Object.assign({id:item.id,name:name.trim()},current()));
    });
    $('#notification-template-delete').on('click', function() {
        var item=selected(); if (!item || item.builtin) return;
        if (window.confirm('Delete saved template "'+item.name+'"? Existing watch settings will not change.'))
            mutate('delete',{id:item.id});
    });
    $('#notification-template-copy').on('click', function() {
        var item=current(), content='Title:\n'+item.title+'\n\nBody:\n'+item.body+'\n\nFormat: '+item.format;
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(content).then(function(){say('Template copied.');},function(){say('Clipboard permission denied.');});
        } else { say('Clipboard API unavailable in this browser.'); }
    });
    $('#notification-template-preview').on('click', function() {
        var item=current();
        if (!item.title.trim() || !item.body.trim()) {
            say('Enter a title and body before previewing.'); return;
        }
        $result.hide(); say('Rendering preview (nothing will be sent)...');
        $.ajax({url:previewEndpoint,type:'POST',contentType:'application/json',headers:headers,
            data:JSON.stringify(Object.assign({},item, {watch_uuid:watchMatch ? watchMatch[1] : null}))})
            .done(function(data) {
                // Do NOT insert rendered template HTML into the DOM. Page-provided
                // title/price/description can contain untrusted markup.
                $('#notification-template-preview-title').text(data.title);
                $('#notification-template-preview-body').text(data.body);
                $('#notification-template-preview-source').text(data.source === 'watch'
                    ? 'Using current Watch data; no notification sent.'
                    : 'Using example data; no notification sent.');
                $result.show(); say('');
            }).fail(function(xhr) {
                say((xhr.responseJSON && xhr.responseJSON.error) || 'Preview failed.');
            });
    });
    reload();
}

function checkDiscordHtmlWarning() {
    var urls = $('textarea.notification-urls').val() || '';
    var format = $('select.notification-format').val() || '';
    var isDiscord = /discord:\/\/|https:\/\/discord(?:app)?\.com\/api/i.test(urls);
    var isHtml = format === 'html' || format === 'htmlcolor';
    if (isDiscord && isHtml) {
        $('#discord-html-format-warning').show();
    } else {
        $('#discord-html-format-warning').hide();
    }
}

// Build a mailto-style Apprise URL from an email address using the configured preset.
// Supports a {TO} token anywhere in the preset; falls back to prefix+address.
function buildEmailUrl(email) {
    var p = (typeof email_notification_prefix !== 'undefined' && email_notification_prefix) ? email_notification_prefix : 'mailto://';
    if (p.indexOf('{TO}') !== -1) {
        return p.replace('{TO}', email);
    }
    return p + email;
}

// Turn a single Apprise URL into a friendly {icon, label} for the recipient chips.
function describeNotificationUrl(url) {
    var u = (url || '').trim();
    if (!u) return null;

    var isEmailPreset = false;
    if (typeof email_notification_prefix !== 'undefined' && email_notification_prefix) {
        var base = email_notification_prefix.indexOf('{TO}') !== -1
            ? email_notification_prefix.split('{TO}')[0]
            : email_notification_prefix;
        isEmailPreset = base && u.indexOf(base) === 0;
    }

    if (/^mailtos?:\/\//i.test(u) || isEmailPreset) {
        var addr = null;
        var toMatch = u.match(/[?&]to=([^&]+)/i);
        if (toMatch) {
            addr = decodeURIComponent(toMatch[1]);
        } else if (isEmailPreset) {
            var base2 = email_notification_prefix.indexOf('{TO}') !== -1
                ? email_notification_prefix.split('{TO}')[0]
                : email_notification_prefix;
            addr = u.substring(base2.length);
        } else {
            var m = u.match(/^mailtos?:\/\/([^?@\/]+@[^?\/]+)/i);
            if (m) addr = m[1];
        }
        return {type: 'email', icon: '✉', label: addr || u};
    }

    var scheme = (u.split('://')[0] || '').toLowerCase();
    var names = {
        discord: 'Discord', tgram: 'Telegram', telegram: 'Telegram', slack: 'Slack',
        tgrams: 'Telegram', gets: 'Webhook', posts: 'Webhook', get: 'Webhook', post: 'Webhook'
    };
    return {type: scheme || 'other', icon: '🔔', label: names[scheme] || (scheme || u)};
}

function notificationLines() {
    return ($('textarea.notification-urls').val() || '')
        .split('\n').map(function (s) { return s.trim(); }).filter(function (s) { return s.length; });
}

// Re-render the recipient chips from the textarea (the textarea stays the source of truth).
function renderNotificationRecipients() {
    var $container = $('#notification-recipients');
    if (!$container.length) return;
    var lines = notificationLines();
    $container.empty();
    if (!lines.length) { $container.hide(); return; }
    $container.show();

    lines.forEach(function (line) {
        var d = describeNotificationUrl(line);
        if (!d) return;
        var $chip = $('<span class="notification-chip"></span>').attr('data-url', line);
        $chip.append($('<span class="notification-chip-icon"></span>').text(d.icon));
        $chip.append($('<span class="notification-chip-label"></span>').text(d.label).attr('title', line));
        var $x = $('<a class="notification-chip-remove" title="Remove">✕</a>');
        $x.on('click', function (e) {
            e.preventDefault();
            removeNotificationLine(line);
        });
        $chip.append($x);
        $container.append($chip);
    });
}

function appendNotificationUrl(url) {
    var $ta = $('textarea.notification-urls');
    var cur = $.trim($ta.val() || '');
    $ta.val(cur ? cur + '\n' + url : url);
    $ta.trigger('input');
}

function removeNotificationLine(line) {
    var $ta = $('textarea.notification-urls');
    var kept = ($ta.val() || '').split('\n').filter(function (s) { return s.trim() !== line.trim(); });
    $ta.val(kept.join('\n'));
    $ta.trigger('input');
}

$(document).ready(function () {
    setupNotificationTemplateLibrary();

    $('textarea.notification-urls, select.notification-format').on('change input', checkDiscordHtmlWarning);
    checkDiscordHtmlWarning();

    // Watch edit can inherit Tag/Global notification addresses; it must be
    // possible to test unsaved Watch message templates with an empty local URL.
    function updateSendTestVisibility() {
        var isWatchEditor = /\/notification\/send-test\/[^/]+(?:\/|$|\?)/.test(
            typeof notification_base_url === 'string' ? notification_base_url : '');
        $('#send-test-notification').toggle(isWatchEditor || notificationLines().length > 0);
    }

    // Keep the friendly chips in sync whenever the raw URLs change (typed or programmatic).
    $('textarea.notification-urls').on('change input', function () {
        renderNotificationRecipients();
        updateSendTestVisibility();
    });
    renderNotificationRecipients();
    updateSendTestVisibility();

    // Email quick-add: the inline field is always visible when a preset is configured.
    function commitEmail() {
        var input = $('#add-email-input')[0];
        var email = $.trim($('#add-email-input').val());
        if (!email) return;
        // Use native email validation if available.
        if (input && input.checkValidity && !input.checkValidity()) {
            input.reportValidity();
            return;
        }
        appendNotificationUrl(buildEmailUrl(email));
        $('#add-email-input').val('').focus();
    }

    $('#add-email-go').click(function (e) {
        e.preventDefault();
        commitEmail();
    });

    $('#add-email-input').on('keydown', function (e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            commitEmail();
        }
    });

    $('#send-test-notification').click(function (e) {
        e.preventDefault();

        data = {
            notification_urls: $('textarea.notification-urls').val(),
            notification_title: $('input.notification-title').val(),
            notification_body: $('textarea.notification-body').val(),
            notification_format: $('select.notification-format').val(),
            tags: $('#tags').val(),
            window_url: window.location.href,
        }

        $('.notifications-wrapper .spinner').fadeIn();
        $('#notification-test-log').show();
        $.ajax({
            type: "POST",
            url: notification_base_url,
            data: data,
            statusCode: {
                400: function (data) {
                    $("#notification-test-log>span").text(data.responseText);
                },
            }
        }).done(function (data) {
            $("#notification-test-log>span").text(data);
        }).fail(function (jqXHR, textStatus, errorThrown) {
            // The server returns a credential-free error explanation for validation
            // and delivery failures. Do not discard it in the generic handler.
            if (jqXHR && jqXHR.responseText) {
                $("#notification-test-log>span").text(jqXHR.responseText);
                return;
            }
            // Handle connection refused or other errors
            if (textStatus === "error" && errorThrown === "") {
                console.error("Connection refused or server unreachable");
                $("#notification-test-log>span").text("Error: Connection refused or server is unreachable.");
            } else {
                console.error("Error:", textStatus, errorThrown);
                $("#notification-test-log>span").text("An error occurred: " + textStatus);
            }
        }).always(function () {
            $('.notifications-wrapper .spinner').hide();
        })
    });
});

