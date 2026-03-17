%% =========================================================================
%  analyse_perturbations_advanced.m
%  Advanced figures for perturbation-testing database.json
%
%  Usage: set DB_PATH below and run. Set SAVE_FIGS = true to write PNGs.
%
%  Figures:
%    Fig A  — Total hits vs probe outcome scatter (smooth trend + annotation)
%    Fig B  — Test kill-power distribution: per project + aggregated
%    Fig C  — Exception type breakdown per project (top 5 only)
%    Fig D  — Probe outcome by unique-tests-hit threshold
% =========================================================================

clear; clc; close all;

% ── Configuration ─────────────────────────────────────────────────────────
DB_PATH   = 'database.json';
SAVE_FIGS = true;
BASE_DIR = fileparts(DB_PATH);
if isempty(BASE_DIR), BASE_DIR = '.'; end

OUT_DIR = fullfile(BASE_DIR, 'analysis_results');
if SAVE_FIGS && ~exist(OUT_DIR, 'dir')
    mkdir(OUT_DIR);
end

% ── Colour palette ────────────────────────────────────────────────────────
C_CLEAN   = [0.45 0.75 0.45];
C_DIRTY   = [0.95 0.80 0.25];
C_SURVIVE = [0.85 0.35 0.35];
C_UNHIT   = [0.72 0.72 0.72];

OUTCOME_COLORS = [C_CLEAN; C_DIRTY; C_SURVIVE; C_UNHIT];
OUTCOME_LABELS = {'Clean Kill','Dirty Kill','Survived','Un-hit'};
OUTCOME_ORDER  = {'Clean Kill','Dirty Kill','Survived','Un-hit'};

set(0,'DefaultAxesFontName','Helvetica','DefaultAxesFontSize',11);
set(0,'DefaultTextFontName','Helvetica');
FIG_W = 1020; FIG_H = 540;

% =========================================================================
%% 0.  Load & parse
% =========================================================================
fprintf('Loading %s ...\n', DB_PATH);
raw = jsondecode(fileread(DB_PATH));

probes     = raw.probes;
test_execs = raw.test_executions;

probe_projects    = {probes.project};
probe_outcomes    = {probes.probe_outcome};
probe_hits        = [probes.total_hits];
probe_unique_hits = [probes.unique_tests_hit];

projects  = unique(probe_projects, 'stable');
nP        = numel(projects);
proj_cmap = lines(nP);

fprintf('Loaded %d probes, %d test executions, %d project(s).\n', ...
        numel(probes), numel(test_execs), nP);

% =========================================================================
%% Helpers
% =========================================================================

function save_fig(fig, out_dir, name)
    png_name = fullfile(out_dir, [name '.png']);
    exportgraphics(fig, png_name, 'Resolution', 300);
    
    pdf_name = fullfile(out_dir, [name '.pdf']);
    exportgraphics(fig, pdf_name, 'ContentType', 'vector', 'BackgroundColor', 'none');
    
    fprintf('  Saved: %s (.png & .pdf)\n', name);
end

function draw_stacked(ax, pct, totals, x_labels, colors, leg_labels, min_pct)
    nG = size(pct,1);
    b  = bar(ax, pct, 'stacked', 'BarWidth', 0.6);
    for k = 1:4
        b(k).FaceColor = colors(k,:);
        b(k).EdgeColor = 'none';
    end
    ax.XTick              = 1:nG;
    ax.XTickLabel         = x_labels;
    ax.XTickLabelRotation = 20;
    ax.YLim               = [0 118];
    ax.YLabel.String      = 'Percentage of probes (%)';
    ax.Box                = 'off';
    ax.YGrid              = 'on';
    ax.GridAlpha          = 0.15;
    legend(ax, leg_labels, 'Location','northeastoutside','Box','off','FontSize',10);
    for i = 1:nG
        text(ax, i, 101 + 118*0.022, sprintf('n=%d', totals(i)), ...
             'HorizontalAlignment','center','FontSize',8.5, ...
             'Color',[0.25 0.25 0.25],'FontWeight','bold');
    end
    for k = 1:4
        for i = 1:nG
            if pct(i,k) >= min_pct
                base = sum(pct(i,1:k-1));
                text(ax, i, base + pct(i,k)/2, sprintf('%.0f%%', pct(i,k)), ...
                     'HorizontalAlignment','center','FontSize',8, ...
                     'Color','w','FontWeight','bold');
            end
        end
    end
end

% =========================================================================
%% Fig A — Total hits vs probe outcome scatter
%
%  WHAT YOU SEE:
%    Each dot is one probe. X = how many times that probe was hit across all
%    test runs (log scale). Y = outcome: Survived (bottom), Dirty Kill (middle),
%    Clean Kill (top), with slight vertical jitter to prevent dots stacking.
%
%    The dark trend line is a SMOOTHED AVERAGE: probes are grouped into
%    equal-width log-spaced hit-count buckets and the average outcome level
%    within each bucket is plotted. A rising trend means probes hit by more
%    tests tend to be killed more reliably. A flat trend is the more
%    interesting finding — it means hitting a probe many times adds no
%    extra detection value (test redundancy).
%
%    r = Pearson correlation between log(hits) and outcome level (0/1/2).
%    r close to 0  → no relationship (redundant coverage).
%    r > 0.2       → some positive relationship (more hits = better kills).
% =========================================================================
fprintf('\nFig A: Hits vs outcome scatter ...\n');

oc_colors_3 = {C_SURVIVE, C_DIRTY, C_CLEAN};

ncols_A = min(nP,3);
nrows_A = ceil(nP/ncols_A);
figA    = figure('Position',[100 100 ncols_A*400 nrows_A*360], 'Color','w');

for i = 1:nP
    mask = strcmp(probe_projects, projects{i}) & ~strcmp(probe_outcomes,'Un-hit');
    h    = probe_hits(mask);
    out  = probe_outcomes(mask);

    y_num = zeros(sum(mask),1);
    for pi = 1:numel(y_num)
        if     strcmp(out{pi},'Clean Kill'),  y_num(pi) = 2;
        elseif strcmp(out{pi},'Dirty Kill'),  y_num(pi) = 1;
        end
    end

    rng(42);
    jitter = (rand(size(y_num)) - 0.5) * 0.28;
    y_jit  = y_num + jitter;

    axA = subplot(nrows_A, ncols_A, i);
    hold(axA,'on');

    for k = 0:2
        sel = y_num == k;
        scatter(axA, h(sel), y_jit(sel), 13, oc_colors_3{k+1}, 'filled', ...
                'MarkerFaceAlpha',0.40, 'HandleVisibility','off');
    end

    % Smooth trend: sliding-window average in log space
    % Use 18 equally-spaced windows in log(h) space, require >=4 probes per window
    max_h = max(h);
    if max_h > 1 && sum(h>0) >= 8
        log_h     = log10(max(h,1));
        log_edges = linspace(0, log10(max_h+1), 20);
        bx = zeros(1, numel(log_edges)-1);
        by = zeros(1, numel(log_edges)-1);
        bv = false(1, numel(log_edges)-1);
        for b = 1:numel(log_edges)-1
            in_b = log_h >= log_edges(b) & log_h < log_edges(b+1);
            if sum(in_b) >= 4
                bx(b) = mean(h(in_b));
                by(b) = mean(y_num(in_b));
                bv(b) = true;
            end
        end
        if sum(bv) >= 3
            % Extra smoothing pass over the bin means (weighted moving avg)
            bx_v = bx(bv);  by_v = by(bv);
            by_sm = by_v;
            for s = 2:numel(by_v)-1
                by_sm(s) = mean(by_v(max(1,s-1):min(end,s+1)));
            end
            plot(axA, bx_v, by_sm, '-', 'Color',[0.15 0.15 0.15], ...
                 'LineWidth',2.5, 'DisplayName','Smoothed avg');
        end
    end

    axA.XScale        = 'log';
    axA.YTick         = [0 1 2];
    axA.YTickLabel    = {'Survived','Dirty Kill','Clean Kill'};
    axA.YLim          = [-0.5 2.5];
    axA.XLabel.String = 'Total hits (log scale)';
    axA.Title.String  = projects{i};
    axA.Title.FontWeight = 'bold';
    axA.Box           = 'off';
    axA.XGrid         = 'on'; axA.YGrid = 'on'; axA.GridAlpha = 0.12;

    if numel(h) >= 5 && max(h) > 1
        cc = corrcoef(log(h+1), y_num);
        r  = cc(1,2);
        text(axA, axA.XLim(2)*0.97, 2.38, sprintf('r = %.2f', cc(1,2)), ...
             'HorizontalAlignment','right','FontSize',9, ...
             'Color',[0.2 0.2 0.2],'FontWeight','bold');
    end
    hold(axA,'off');
end

% Outcome legend (manual patches on figure)
annotation_ax = axes(figA,'Position',[0 0 1 1],'Visible','off');
hold(annotation_ax,'on');
for k = 1:3
    patch(annotation_ax, NaN, NaN, oc_colors_3{k}, 'EdgeColor','none', ...
          'DisplayName', OUTCOME_LABELS{4-k});
end
patch(annotation_ax, NaN, NaN, [0.15 0.15 0.15], 'EdgeColor','none', ...
      'DisplayName','Smoothed avg trend');
legend(annotation_ax,'Location','southoutside','Orientation','horizontal', ...
       'Box','off','FontSize',9);
hold(annotation_ax,'off');

sgtitle(figA, 'Total Hits vs Probe Outcome — per Project', 'FontWeight','bold','FontSize',13);

if SAVE_FIGS, save_fig(figA, OUT_DIR, 'figA_hits_vs_outcome'); end

% =========================================================================
%% Fig B — Test kill-power distribution: per project + aggregated
%
%  WHAT YOU SEE:
%    For each test, we count how many distinct probes it uniquely clean-kills
%    (assertion-level failures). Tests are sorted descending by this count
%    and plotted as a bar chart — the tallest bars on the left are the
%    "power tests" that do the most perturbation detection work.
%    The black cumulative line shows what % of total clean kills are
%    accounted for by the leftmost X% of tests.
%
%    Small multiples show each project. The final panel (bottom-right or
%    separate figure) shows the AVERAGE across all projects, making the
%    Pareto shape visible at the benchmark-suite level.
%
%    Key finding: if the 80% cumulative line is crossed early (e.g. at 10%),
%    that means 10% of tests account for 80% of all clean kills — the vast
%    majority of tests are "passengers" that add no perturbation detection.
% =========================================================================
fprintf('Fig B: Test kill-power distribution ...\n');

exec_outcomes_te = {test_execs.test_outcome};
exec_tests_te    = {test_execs.test};
exec_probes_te   = [test_execs.probe_id];
exec_projects_te = {test_execs.project};

% Compute test power per project
test_power_proj  = cell(nP,1);
pctile80_proj    = NaN(nP,1);   % percentile at which 80% kills reached

for i = 1:nP
    proj_mask_te = strcmp(exec_projects_te, projects{i});
    clean_mask   = proj_mask_te & strcmp(exec_outcomes_te,'FAIL by Assert');
    tests_here   = unique(exec_tests_te(proj_mask_te));
    n_t          = numel(tests_here);
    tp           = zeros(n_t,1);
    for t = 1:n_t
        t_m   = proj_mask_te & strcmp(exec_tests_te, tests_here{t}) & clean_mask;
        tp(t) = numel(unique(exec_probes_te(t_m)));
    end
    test_power_proj{i} = sort(tp,'descend');
    cum = cumsum(test_power_proj{i});
    tot = sum(tp);
    if tot > 0
        idx80 = find(cum/tot >= 0.80, 1,'first');
        if ~isempty(idx80)
            pctile80_proj(i) = idx80/n_t*100;
        end
    end
end

% Build an aggregated average:
% Normalise each project's power vector to percentile bins (100 bins),
% then average across projects — gives a "typical" Pareto shape.
n_bins_agg = 100;
power_norm = zeros(nP, n_bins_agg);
for i = 1:nP
    tp_s = test_power_proj{i};
    n_t  = numel(tp_s);
    if n_t == 0, continue; end
    % Interpolate to 100 equal percentile points
    x_orig = linspace(0, 100, n_t);
    x_new  = linspace(0, 100, n_bins_agg);
    tot    = max(sum(tp_s), 1);
    power_norm(i,:) = interp1(x_orig, tp_s/tot*100, x_new, 'linear', 0);
end
avg_power = mean(power_norm, 1);
cum_avg   = cumsum(avg_power) / sum(avg_power) * 100;
idx80_avg = find(cum_avg >= 80, 1,'first');

% Layout: small multiples + one aggregated panel
ncols_B = min(nP,3);
nrows_B = ceil(nP/ncols_B);
% Add one extra slot for the aggregated panel
total_slots = nrows_B * ncols_B;
need_extra  = (nP == total_slots);   % no spare slot

if need_extra
    ncols_B = min(nP+1, 3);
    nrows_B = ceil((nP+1)/ncols_B);
end

figB = figure('Position',[100 100 ncols_B*400 nrows_B*330], 'Color','w');

for i = 1:nP
    tp_s  = test_power_proj{i};
    n_t   = numel(tp_s);
    pct_x = (1:n_t)/n_t*100;
    cum_k = cumsum(tp_s);
    tot_k = sum(tp_s);

    axB = subplot(nrows_B, ncols_B, i);
    yyaxis(axB,'left');
    bar(axB, pct_x, tp_s, 1, 'FaceColor',C_CLEAN, 'EdgeColor','none', 'FaceAlpha',0.75);
    axB.YColor        = C_CLEAN * 0.65;
    axB.YLabel.String = 'Clean-killed probes per test';

    yyaxis(axB,'right');
    if tot_k > 0
        plot(axB, pct_x, cum_k/tot_k*100, '-', 'Color',[0.15 0.15 0.15], 'LineWidth',2);
        if ~isnan(pctile80_proj(i))
            xline(axB, pctile80_proj(i), '--', 'Color',[0.5 0.5 0.5], 'LineWidth',1.2, ...
                  'HandleVisibility','off');
            text(axB, pctile80_proj(i)+1, 74, ...
                 sprintf('%.0f%% of tests\n→ 80%% of kills', pctile80_proj(i)), ...
                 'FontSize',7.5,'Color',[0.35 0.35 0.35]);
        end
    end
    axB.YColor        = [0.15 0.15 0.15];
    axB.YLabel.String = 'Cumulative clean kills (%)';
    axB.YLim          = [0 105];

    axB.XLabel.String    = 'Test percentile — sorted by kill power (desc.)';
    axB.Title.String     = projects{i};
    axB.Title.FontWeight = 'bold';
    axB.Box              = 'off';
    axB.XGrid            = 'on'; axB.GridAlpha = 0.12;

    n_killers = sum(tp_s > 0);
    text(axB, 97, 8, sprintf('n=%d tests\n%d kill ≥1', n_t, n_killers), ...
         'HorizontalAlignment','right','FontSize',7.5,'Color',[0.4 0.4 0.4]);
end

sgtitle(figB, 'Test Kill-Power Distribution — per Project', 'FontWeight','bold','FontSize',13);

if SAVE_FIGS, save_fig(figB, OUT_DIR, 'figB_test_power'); end

% Fig B2 — aggregated average (separate figure)
pct_agg = linspace(0, 100, n_bins_agg);
figB2 = figure('Position',[100 100 700 480], 'Color','w');
axBA  = axes(figB2);
yyaxis(axBA,'left');
bar(axBA, pct_agg, avg_power, 1, 'FaceColor',C_CLEAN, 'EdgeColor','none', 'FaceAlpha',0.80);
axBA.YColor        = C_CLEAN * 0.65;
axBA.YLabel.String = 'Avg clean kills per test (normalised)';
yyaxis(axBA,'right');
plot(axBA, pct_agg, cum_avg, '-', 'Color',[0.15 0.15 0.15], 'LineWidth',2.5);
if ~isempty(idx80_avg)
    xline(axBA, pct_agg(idx80_avg), '--', 'Color',[0.5 0.5 0.5], 'LineWidth',1.5, ...
          'HandleVisibility','off');
    text(axBA, pct_agg(idx80_avg)+1, 74, ...
         sprintf('%.0f%% of tests account for 80%% of kills', pct_agg(idx80_avg)), ...
         'FontSize',9,'Color',[0.25 0.25 0.25],'FontWeight','bold');
end
axBA.YColor        = [0.15 0.15 0.15];
axBA.YLabel.String = 'Cumulative clean kills (%)';
axBA.YLim          = [0 105];
axBA.XLabel.String = 'Test percentile (%) — sorted by kill power, normalised across projects';
axBA.Title.String  = 'Test Kill-Power Distribution — Aggregated Across All Projects';
axBA.Title.FontWeight = 'bold';
axBA.Box           = 'off';
axBA.XGrid         = 'on'; axBA.GridAlpha = 0.12;

if SAVE_FIGS, save_fig(figB2, OUT_DIR, 'figB2_test_power_aggregated'); end

% =========================================================================
%% Fig C — Exception type breakdown per project (top 5 only)
%
%  For dirty-kill test executions, shows what exception types the test suite
%  "sees" when a probe is perturbed. Capped at the top 5 globally most
%  frequent exceptions + an "Other" bucket to keep the chart clean.
%
%  If all projects show the same dominant exception (typically
%  NullPointerException from nullified Object probes), that is itself a
%  finding: perturbation detection is happening via unintended crashes
%  rather than deliberate assertions — which is exactly what Dirty Kills are.
% =========================================================================
fprintf('Fig C: Exception breakdown per project ...\n');

exec_outcomes_te2 = {test_execs.test_outcome};
exec_excs_te      = {test_execs.exception};
exec_proj_te2     = {test_execs.project};

dirty_te  = strcmp(exec_outcomes_te2,'FAIL by Exception');
all_excs  = exec_excs_te(dirty_te);
all_excs  = all_excs(~strcmp(all_excs,'none') & ~strcmp(all_excs,'Unknown'));

if isempty(all_excs)
    fprintf('  No exceptions found — skipping Fig C.\n');
else
    [exc_u, ~, ic_u] = unique(all_excs);
    exc_glob_cnt = accumarray(ic_u(:), 1);
    [~, exc_sort] = sort(exc_glob_cnt,'descend');
    top_exc = exc_u(exc_sort(1:min(5, numel(exc_u))));   % TOP 5 ONLY
    nExc    = numel(top_exc);

    exc_matrix = zeros(nP, nExc+1);
    for i = 1:nP
        proj_dirty = dirty_te & strcmp(exec_proj_te2, projects{i});
        proj_excs  = exec_excs_te(proj_dirty);
        proj_excs  = proj_excs(~strcmp(proj_excs,'none') & ~strcmp(proj_excs,'Unknown'));
        tot_proj   = numel(proj_excs);
        if tot_proj == 0, continue; end
        for e = 1:nExc
            exc_matrix(i,e) = sum(strcmp(proj_excs, top_exc{e}));
        end
        exc_matrix(i,end) = tot_proj - sum(exc_matrix(i,1:nExc));
    end

    exc_totals = sum(exc_matrix,2);
    exc_pct    = exc_matrix ./ max(exc_totals,1) * 100;

    % 5 colours + grey for Other — clean and distinguishable
    exc_cmap = [0.95 0.80 0.25;   % yellow
                0.85 0.35 0.35;   % red
                0.40 0.62 0.82;   % blue
                0.55 0.78 0.50;   % green
                0.80 0.50 0.75;   % purple
                0.72 0.72 0.72];  % grey = Other

    exc_labels_all = [top_exc(:); {'Other'}];

    figC = figure('Position',[100 100 FIG_W FIG_H], 'Color','w');
    axC  = axes(figC);
    bC   = bar(axC, exc_pct, 'stacked', 'BarWidth',0.6);
    for e = 1:nExc+1
        bC(e).FaceColor = exc_cmap(e,:);
        bC(e).EdgeColor = 'none';
    end

    axC.XTick              = 1:nP;
    axC.XTickLabel         = projects;
    axC.XTickLabelRotation = 20;
    axC.YLim               = [0 118];
    axC.YLabel.String      = 'Share of dirty-kill exceptions (%)';
    axC.Title.String       = 'Exception Type Profile per Project — Dirty Kills (top 5)';
    axC.Title.FontWeight   = 'bold';
    axC.Box                = 'off';
    axC.YGrid              = 'on'; axC.GridAlpha = 0.15;
    legend(axC, exc_labels_all, 'Location','northeastoutside','Box','off','FontSize',10);

    for i = 1:nP
        text(axC, i, 102, sprintf('n=%d', exc_totals(i)), ...
             'HorizontalAlignment','center','FontSize',8.5, ...
             'Color',[0.25 0.25 0.25],'FontWeight','bold');
        cum_exc = 0;
        for e = 1:nExc+1
            if exc_pct(i,e) >= 7
                text(axC, i, cum_exc + exc_pct(i,e)/2, sprintf('%.0f%%',exc_pct(i,e)), ...
                     'HorizontalAlignment','center','FontSize',8, ...
                     'Color','w','FontWeight','bold');
            end
            cum_exc = cum_exc + exc_pct(i,e);
        end
    end

    if SAVE_FIGS, save_fig(figC, OUT_DIR, 'figC_exception_breakdown'); end
end

% =========================================================================
%% Fig D — Probe outcome by unique-tests-hit threshold
%
%  WHAT YOU SEE:
%    Probes are grouped by how many DISTINCT tests exercise them:
%      Bin 1: exactly 1 test hits this probe
%      Bin 2: 2–5 tests
%      Bin 3: 6–15 tests
%      Bin 4: 16+ tests
%
%    Left panel: 100% stacked outcome bars (aggregated across all projects).
%    Right panel: grouped bar showing the CLEAN KILL RATE per bin for each
%    project side-by-side. This replaces the tangled line chart — each
%    project's bar cluster sits next to the others at the same bin, making
%    cross-project comparison easy without any lines crossing.
%
%    Key question: does more test coverage of a probe actually improve its
%    chance of being killed? A rising clean kill % from bin 1 → bin 4
%    means yes. A flat pattern means adding more tests to already-covered
%    probes brings no extra perturbation-detection value.
% =========================================================================
fprintf('Fig D: Outcome by coverage depth ...\n');

bins_D       = {1, [2 5], [6 15], 16};
bin_labels_D = {'Exactly 1 test','2–5 tests','6–15 tests','16+ tests'};
nBins_D      = numel(bins_D);
exec_mask_D  = ~strcmp(probe_outcomes,'Un-hit');

% Helper: which bin does a unique_hits value fall in?
function b = get_bin(u, bins)
    b = 0;
    for bi = 1:numel(bins)
        bd = bins{bi};
        if numel(bd) == 1 && bi < numel(bins)
            if u == bd(1), b = bi; return; end
        elseif numel(bd) == 2
            if u >= bd(1) && u <= bd(2), b = bi; return; end
        else
            if u >= bd(1), b = bi; return; end
        end
    end
end

% Aggregated outcome matrix
pct_D  = zeros(nBins_D, 4);
tot_D  = zeros(nBins_D, 1);
for b = 1:nBins_D
    bd = bins_D{b};
    if     numel(bd)==1 && b<nBins_D, in_bin = probe_unique_hits == bd(1);
    elseif numel(bd)==2,               in_bin = probe_unique_hits >= bd(1) & probe_unique_hits <= bd(2);
    else,                              in_bin = probe_unique_hits >= bd(1);
    end
    in_bin   = in_bin & exec_mask_D;
    tot_D(b) = sum(in_bin);
    for k = 1:4
        pct_D(b,k) = sum(in_bin & strcmp(probe_outcomes,OUTCOME_ORDER{k})) / max(tot_D(b),1) * 100;
    end
end

% Per-project clean kill rate per bin
ck_proj_D = NaN(nP, nBins_D);
for i = 1:nP
    pm = strcmp(probe_projects, projects{i}) & exec_mask_D;
    for b = 1:nBins_D
        bd = bins_D{b};
        if     numel(bd)==1 && b<nBins_D, in_bin = probe_unique_hits == bd(1);
        elseif numel(bd)==2,               in_bin = probe_unique_hits >= bd(1) & probe_unique_hits <= bd(2);
        else,                              in_bin = probe_unique_hits >= bd(1);
        end
        in_bin = in_bin & pm;
        if sum(in_bin) < 3, continue; end
        ck_proj_D(i,b) = sum(in_bin & strcmp(probe_outcomes,'Clean Kill')) / sum(in_bin) * 100;
    end
end

figD = figure('Position',[100 100 FIG_W FIG_H], 'Color','w');

% Left: 100% stacked (aggregated)
axDL = subplot(1,2,1);
draw_stacked(axDL, pct_D, tot_D, bin_labels_D, OUTCOME_COLORS, OUTCOME_LABELS, 5);
axDL.XLabel.String    = 'Number of distinct tests hitting probe';
axDL.Title.String     = 'Outcome by Coverage Depth — All Projects';
axDL.Title.FontWeight = 'bold';
axDL.XTickLabelRotation = 12;

% Right: grouped bar — clean kill rate per project per bin
axDR = subplot(1,2,2);
bDR  = bar(axDR, ck_proj_D', 'grouped', 'BarWidth',0.8);
for i = 1:nP
    bDR(i).FaceColor = proj_cmap(i,:);
    bDR(i).EdgeColor = 'none';
    bDR(i).FaceAlpha = 0.88;
end

% Aggregated clean kill rate overlay as a black dashed line
agg_ck_D = pct_D(:,1);
hold(axDR,'on');
plot(axDR, 1:nBins_D, agg_ck_D, 'k--o', 'LineWidth',2.5, 'MarkerSize',7, ...
     'MarkerFaceColor','k', 'DisplayName','All Projects avg');
hold(axDR,'off');

axDR.XTick              = 1:nBins_D;
axDR.XTickLabel         = bin_labels_D;
axDR.XTickLabelRotation = 12;
axDR.YLim               = [0 100];
axDR.XLim               = [0.5 nBins_D+0.5];
axDR.YLabel.String      = 'Clean kill rate (%)';
axDR.XLabel.String      = 'Number of distinct tests hitting probe';
axDR.Title.String       = 'Clean Kill Rate per Project';
axDR.Title.FontWeight   = 'bold';
axDR.Box                = 'off';
axDR.YGrid              = 'on'; axDR.XGrid = 'on'; axDR.GridAlpha = 0.14;
legend(axDR, [projects, {'All Projects avg'}], ...
       'Location','northwest','Box','off','FontSize',9);

sgtitle(figD, 'Probe Outcome by Number of Tests Hitting It', 'FontWeight','bold','FontSize',13);

if SAVE_FIGS, save_fig(figD, OUT_DIR, 'figD_outcome_by_coverage_depth'); end

% =========================================================================
fprintf('\nDone. All advanced figures generated.\n');
if SAVE_FIGS, fprintf('PNGs saved to: %s\n', OUT_DIR); end