// Restock price/stock timeline - time-scaled stepped SVG history.
// Neutral stepped price line; coloured dots indicate stock state.
//
// Two consumers:
//   * the restock diff page (#restock-graph), which fetches window.restock_data_url and also
//     builds the data table below it; and
//   * the watchlist inline roll-down, which calls window.renderRestockGraph(el, series, currency, i18n).
//
// Series shape (oldest -> newest): [{timestamp: <epoch sec>, price: <float|null>, in_stock: <bool|null>}]

(function ($) {
    'use strict';

    const SVG_NS = 'http://www.w3.org/2000/svg';
    const COLOR_IN = '#1fa463';   // in stock = green
    const COLOR_OUT = '#e74c3c';  // out of stock = red
    const COLOR_UNKNOWN = '#999'; // stock state not known
    const HEIGHT = 250;          // default (diff page); the inline watchlist graph passes a shorter one
    const PAD = { top: 20, right: 24, bottom: 36, left: 70 };
    const MAX_X_LABELS = 4;       // keep the date axis uncluttered

    const DEFAULT_I18N = { in_stock: 'In stock', out_of_stock: 'Out of stock',
        no_data: 'No price data available to graph yet.', load_error: 'Could not load price history.',
        changes: 'Changes', checks: 'Checks', avg_price: 'Average price',
        price_low: 'Currently low', price_typical: 'Currently typical', price_high: 'Currently high',
        // {pct} is substituted with an already-formatted percentage, e.g. "80%". The percent sign is
        // NOT part of the msgid on purpose: a bare "%" followed by a letter (" of") parses as a
        // python-format conversion ("% o"), which makes pybabel reject any translation of it.
        cheaper_than: 'cheaper than {pct} of tracked prices',
        pricier_than: 'more expensive than {pct} of tracked prices',
        typical_note: 'around the usual price', avg_label: 'avg' };
    const OVERLAY_MIN_POINTS = 5; // need enough history for low/typical/high to be meaningful

    function el(name, attrs) {
        const e = document.createElementNS(SVG_NS, name);
        for (const k in attrs) e.setAttribute(k, attrs[k]);
        return e;
    }

    function stockColor(inStock) {
        if (inStock === true) return COLOR_IN;
        if (inStock === false) return COLOR_OUT;
        return COLOR_UNKNOWN;
    }

    // X-axis label: day + short month + short year, e.g. "21 Jun '25".
    function fmtAxisDate(epoch, span) {
        const d = new Date(epoch * 1000);
        if (span < 86400) return d.toLocaleTimeString(undefined, {hour: 'numeric', minute: '2-digit'});
        if (span < 7 * 86400) return d.toLocaleDateString(undefined, {month: 'short', day: 'numeric', hour: 'numeric'});
        return d.toLocaleDateString(undefined, {month: 'short', day: 'numeric', year: '2-digit'});
    }

    function fmtDateTime(epoch) {
        return new Date(epoch * 1000).toLocaleString(undefined, {
            year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
        });
    }

    function fmtPrice(v, currency) {
        if (v === null || v === undefined || !Number.isFinite(Number(v))) return '—';
        const amount = Number(v);
        const iso = (currency || '').toUpperCase();
        try {
            if (/^[A-Z]{3}$/.test(iso)) return new Intl.NumberFormat(undefined, {
                style: 'currency', currency: iso, minimumFractionDigits: 2,
                maximumFractionDigits: 2
            }).format(amount);
        } catch (e) { /* Unknown currencies fall back to plain numbers. */ }
        return (currency ? currency + ' ' : '') + amount.toLocaleString(undefined, {
            minimumFractionDigits: 2, maximumFractionDigits: 2
        });
    }

    function downsampleObservations(series, target) {
        if (series.length <= target) return series;
        const selected = new Set([0, series.length - 1]);
        const chunkSize = Math.max(1, Math.ceil(series.length / Math.max(1, Math.floor(target / 4))));
        for (let i = 0; i < series.length; i += chunkSize) {
            let min = null, max = null;
            const end = Math.min(i + chunkSize, series.length);
            selected.add(i); selected.add(end - 1);
            for (let j = i; j < end; j++) {
                const v = series[j].price;
                if (v === null || v === undefined) {
                    // Keep only run boundaries; thousands of missing observations
                    // must not create thousands of SVG nodes.
                    if (j === 0 || series[j - 1].price !== null) selected.add(j);
                    if (j + 1 === series.length || series[j + 1].price !== null) selected.add(j);
                } else {
                    if (min === null || v < series[min].price) min = j;
                    if (max === null || v > series[max].price) max = j;
                }
            }
            if (min !== null) selected.add(min);
            if (max !== null) selected.add(max);
        }
        return Array.from(selected).sort((a, b) => a - b).map(i => series[i]);
    }

    function draw($container, series, currency, i18n, summary, height) {
        const observations = (series || []).filter(p => p && Number.isFinite(Number(p.timestamp)))
            .slice().sort((a, b) => a.timestamp - b.timestamp);
        const valid = observations.filter(p => p.price !== null && p.price !== undefined && Number.isFinite(Number(p.price)));
        const prices = valid.map(p => Number(p.price));
        const count = observations.length;
        const latest = valid.length ? valid[valid.length - 1] : null;
        const lowest = valid.length ? prices.reduce((a, b) => Math.min(a, b), Infinity) : null;
        const highest = valid.length ? prices.reduce((a, b) => Math.max(a, b), -Infinity) : null;
        const average = valid.length ? prices.reduce((a, b) => a + b, 0) / prices.length : null;
        const $panel = $('<div class="rg-panel"></div>');
        const $header = $('<div class="rg-summary"></div>');
        [
            [i18n.latest_price || 'Latest valid', latest ? fmtPrice(latest.price, latest.currency || currency) : '—'],
            [i18n.lowest_price || 'Lowest', fmtPrice(lowest, currency)],
            [i18n.highest_price || 'Highest', fmtPrice(highest, currency)]
        ].forEach(([label, value]) => {
            const $item = $('<div class="rg-summary-item"></div>');
            $item.append($('<span class="rg-summary-label"></span>').text(label));
            $item.append($('<strong class="rg-summary-value"></strong>').text(value));
            $header.append($item);
        });
        $panel.append($header);

        if (valid.length < 2) {
            const $empty = $('<div class="rg-empty"></div>');
            $empty.append($('<span class="rg-empty-icon" aria-hidden="true">▥</span>'));
            $empty.append($('<strong></strong>').text(valid.length === 1 ?
                (i18n.one_record || 'Only one price record available') :
                (i18n.no_data || 'No price data available yet')));
            $empty.append($('<span></span>').text(valid.length === 1 ?
                (i18n.more_checks || 'A price trend will appear after another valid price check.') :
                (i18n.waiting_price || 'Price history will appear once valid prices are recorded.')));
            if (latest) $empty.append($('<div class="rg-empty-record"></div>')
                .append($('<span></span>').text(fmtDateTime(latest.timestamp)))
                .append($('<strong></strong>').text(fmtPrice(latest.price, latest.currency || currency))));
            $panel.append($empty);
        } else {
            const plotHeight = height || HEIGHT;
            const width = Math.max($container.width() || 0, 320);
            const span = Math.max(0, observations[observations.length - 1].timestamp - observations[0].timestamp);
            const minPrice = lowest, maxPrice = highest;
            // Keep tiny price movements from looking like dramatic crashes.
            const minDomainSpan = Math.max(1, Math.abs((minPrice + maxPrice) / 2) * 0.02);
            const domainSpan = Math.max(maxPrice - minPrice, minDomainSpan);
            const center = (maxPrice + minPrice) / 2;
            const domainMin = center - domainSpan * 0.6;
            const domainMax = center + domainSpan * 0.6;
            const tickValues = [domainMax, center, domainMin];
            const left = Math.max(PAD.left, ...tickValues.map(v => fmtPrice(v, currency).length * 7 + 16));
            const innerW = Math.max(1, width - left - PAD.right);
            const innerH = plotHeight - PAD.top - PAD.bottom;
            const firstTime = observations[0].timestamp;
            const x = p => left + (span ? (p.timestamp - firstTime) / span : 0.5) * innerW;
            const y = p => PAD.top + (domainMax - p) / (domainMax - domainMin) * innerH;
            const chart = el('svg', {width: width, height: plotHeight, role: 'img',
                'aria-label': 'Price history over time'});
            const points = downsampleObservations(observations, Math.max(70, Math.min(250, Math.floor(innerW / 3))));
            tickValues.forEach(tick => {
                const yy = y(tick);
                chart.appendChild(el('line', {class: 'rg-axis', x1: left, y1: yy, x2: width - PAD.right, y2: yy}));
                const label = el('text', {class: 'rg-label', x: left - 9, y: yy + 4, 'text-anchor': 'end'});
                label.textContent = fmtPrice(tick, currency);
                chart.appendChild(label);
            });
            if (summary && summary.count >= OVERLAY_MIN_POINTS &&
                    Number.isFinite(Number(summary.p25)) && Number.isFinite(Number(summary.p75))) {
                const top = y(Math.max(summary.p25, summary.p75));
                const bottom = y(Math.min(summary.p25, summary.p75));
                chart.appendChild(el('rect', {class: 'rg-band', x: left, y: top,
                    width: innerW, height: Math.max(0, bottom - top)}));
            }
            let path = '';
            let previous = null;
            const visibleDots = [];
            points.forEach(p => {
                if (p.price === null || p.price === undefined || !Number.isFinite(Number(p.price))) {
                    previous = null;
                    return;
                }
                if (previous && p.currency && previous.currency && p.currency !== previous.currency) previous = null;
                const xx = x(p), yy = y(Number(p.price));
                path += previous ? ` H ${xx.toFixed(1)} V ${yy.toFixed(1)}` : ` M ${xx.toFixed(1)} ${yy.toFixed(1)}`;
                previous = p;
                visibleDots.push({x: xx, y: yy, point: p});
            });
            chart.appendChild(el('path', {class: 'rg-line', d: path.trim(), fill: 'none',
                'stroke-width': 2.5, 'stroke-linecap': 'round', 'stroke-linejoin': 'round'}));
            visibleDots.forEach(({x: xx, y: yy, point}) => {
                chart.appendChild(el('circle', {class: 'rg-dot', cx: xx, cy: yy, r: 3.5,
                    fill: stockColor(point.in_stock)}));
            });
            // Use observed times and suppress repeated labels when checks occur on one day.
            const labelCount = span === 0 ? 1 : Math.min(MAX_X_LABELS, Math.max(2, Math.floor(innerW / 135)));
            let previousLabel = '';
            for (let i = 0; i < labelCount; i++) {
                const time = firstTime + span * (labelCount === 1 ? 0.5 : i / (labelCount - 1));
                const labelText = fmtAxisDate(time, span);
                if (labelText === previousLabel) continue;
                previousLabel = labelText;
                const t = el('text', {class: 'rg-label', x: left + innerW *
                    (labelCount === 1 ? 0.5 : i / (labelCount - 1)), y: plotHeight - 9,
                    'text-anchor': i === 0 ? 'start' : i === labelCount - 1 ? 'end' : 'middle'});
                t.textContent = labelText;
                chart.appendChild(t);
            }
            const $plot = $('<div class="rg-plot"></div>').append(chart);
            const $tip = $('<div class="rg-tooltip" role="tooltip"></div>').appendTo($plot);
            visibleDots.forEach(({x: xx, y: yy, point}) => {
                const hit = el('circle', {cx: xx, cy: yy, r: 13, fill: 'transparent',
                    style: 'cursor: crosshair;'});
                chart.appendChild(hit);
                $(hit).on('mouseenter mousemove', function (event) {
                    $tip.empty().append($('<strong></strong>').text(fmtPrice(point.price, point.currency || currency)))
                        .append($('<span></span>').text(fmtDateTime(point.timestamp) +
                            (point.in_stock === null || point.in_stock === undefined ? '' :
                            ' · ' + (point.in_stock ? i18n.in_stock : i18n.out_of_stock))));
                    $tip.show();
                    const bounds = $plot[0].getBoundingClientRect();
                    let atX = event.clientX - bounds.left + 12;
                    if (atX + $tip.outerWidth() > $plot.width()) atX = Math.max(0, atX - $tip.outerWidth() - 24);
                    $tip.css({left: atX + 'px', top: Math.max(0, event.clientY - bounds.top - 45) + 'px'});
                }).on('mouseleave', () => $tip.hide());
            });
            $panel.append($plot);
            const $foot = $('<div class="rg-footer"></div>');
            $foot.append($('<span></span>').text((i18n.avg_price || 'Average price') + ': ' + fmtPrice(average, currency)));
            const $meta = $('<span class="rg-footer-meta"></span>');
            $meta.append($('<span></span>').text(count + ' ' + (i18n.checks || 'checks')));
            const $legend = $('<span class="rg-footer-legend"></span>');
            $legend.append($('<span class="rg-mini-dot rg-mini-in"></span>'));
            $legend.append($('<span></span>').text(i18n.in_stock || 'In stock'));
            $legend.append($('<span class="rg-mini-dot rg-mini-out"></span>'));
            $legend.append($('<span></span>').text(i18n.out_of_stock || 'Out of stock'));
            $meta.append($legend);
            $foot.append($meta);
            $panel.append($foot);
        }
        $container.empty().append($panel);
    }

    function buildTable($table, series, currency, i18n) {
        const $tbody = $table.find('tbody');
        if (!$tbody.length) return;
        $tbody.empty();
        series.slice(-500).reverse().forEach(p => {
            let stock = '-';
            if (p.in_stock === true) stock = $('<span class="restock-badge in-stock"></span>').text(i18n.in_stock);
            else if (p.in_stock === false) stock = $('<span class="restock-badge out-of-stock"></span>').text(i18n.out_of_stock);
            const price = (p.price !== null && p.price !== undefined) ? fmtPrice(p.price, p.currency || currency) : '-';
            $('<tr></tr>')
                .append($('<td></td>').text(fmtDateTime(p.timestamp)))
                .append($('<td></td>').append(stock))
                .append($('<td></td>').text(price))
                .appendTo($tbody);
        });
    }

    // Redraw a graph only if its container width actually changed (skips redundant redraws and
    // prevents ResizeObserver feedback loops).
    function redraw($c) {
        const ctx = $c.data('rg');
        if (!ctx) return;
        const w = Math.round($c.width());
        if (w === ctx.lastWidth) return;
        ctx.lastWidth = w;
        draw($c, ctx.series, ctx.currency, ctx.i18n, ctx.summary, ctx.height);
    }

    // Watch the container's own size, not just the window: the content area also changes width
    // when the action sidebar expands on hover (no window 'resize' event fires for that).
    const hasRO = typeof ResizeObserver !== 'undefined';
    let ro = null;
    if (hasRO) {
        let roTimer;
        const pending = new Set();
        ro = new ResizeObserver(function (entries) {
            entries.forEach(e => pending.add(e.target));
            clearTimeout(roTimer);
            roTimer = setTimeout(function () {
                pending.forEach(t => redraw($(t)));
                pending.clear();
            }, 120);
        });
    } else {
        // Fallback for browsers without ResizeObserver: window resize only.
        let resizeTimer;
        $(window).on('resize.restockgraph', function () {
            clearTimeout(resizeTimer);
            resizeTimer = setTimeout(function () {
                $('.js-restock-graph').each(function () { redraw($(this)); });
            }, 150);
        });
    }

    // Public reusable renderer. Stores its context on the element and observes the element so
    // it redraws on any size change; usable from anywhere (e.g. the watchlist inline roll-down).
    window.renderRestockGraph = function (container, series, currency, i18n, summary, height) {
        const $c = $(container);
        if (!$c.length) return;
        const merged = $.extend({}, DEFAULT_I18N);
        Object.entries(i18n || {}).forEach(([key, value]) => { if (value !== undefined && value !== null) merged[key] = value; });
        // Seed lastWidth to the current width so the immediate ResizeObserver callback (which
        // fires once on observe()) doesn't trigger a redundant redraw.
        $c.addClass('js-restock-graph').data('rg', {
            series: series || [], currency: currency || '', i18n: merged, summary: summary || null,
            height: height || HEIGHT, lastWidth: Math.round($c.width())
        });
        draw($c, series || [], currency || '', merged, summary || null, height || HEIGHT);
        if (ro) {
            try { ro.unobserve($c[0]); } catch (e) {}
            ro.observe($c[0]);
        }
    };

    // Diff page bootstrap: fetch the timeline, render the graph + the data table.
    $(function () {
        const $container = $('#restock-graph');
        if (!$container.length || !window.restock_data_url) return;
        const i18n = $.extend({}, DEFAULT_I18N, window.restock_i18n || {});
        let requestId = 0;
        function loadRange() {
        const range = $('#restock-history-range').val() || '30d';
        const current = ++requestId;
        $.getJSON(window.restock_data_url, {range: range}).done(function (data) {
            if (current !== requestId) return;
            const series = (data && data.series) || [];
            window.renderRestockGraph($container, series, (data && data.currency) || '', i18n, (data && data.summary) || null);
            buildTable($('#restock-history-table'), series, (data && data.currency) || '', i18n);
        }).fail(function () {
            if (current !== requestId) return;
            $container.html($('<p class="pure-form-message-inline"></p>').text(i18n.load_error));
        });
        }
        $('#restock-history-range').on('change', loadRange);
        loadRange();
    });

})(jQuery);
