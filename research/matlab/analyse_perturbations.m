%% =========================================================================
%  analyse_perturbations.m
%  Visualise a perturbation-testing database.json produced by run_agent_db.py
%
%  Usage:
%    1. Set DB_PATH to your database.json location
%    2. Run — set SAVE_FIGS = true to write PNGs alongside the database
%
%  Figures:
%    Fig 1  — Probe outcome per project + aggregated (100% stacked)
%    Fig 2  — Probe outcome by operator type aggregated (100% stacked)
%    Fig 3  — CLEAN kill-rate heatmap: projects x operator types
%    Fig 4  — Unique probes vs avg hits per probe, per project + overall
%    Fig 5  — Exception type frequency across dirty kills
%    Fig 6  — Hit-count rank scatter per project (small multiples)
%    Fig 7  — Hit-count rank scatter aggregated across all projects
%    Fig 8  — Test execution efficiency: full suite vs actual tests run per probe
%    Fig 9  — Per-probe test reduction distribution (% of suite needed)
% =========================================================================

clear; clc; close all;

% ── Configuration ─────────────────────────────────────────────────────────
DB_PATH   = '../data/database.json';

% ── Full test suite sizes per project ─────────────────────────────────────
% Set the total number of tests in each project's test suite.
% This is used to compute how many tests the tool SKIPS per probe.
% Get these numbers from: mvn test | grep "Tests run:" (the final summary line)
% Keys must exactly match the project "name" field in database.json.
% If a project is not listed here, it will be estimated from the data.
FULL_SUITE_SIZES = containers.Map( ...
    {'JSemVer',  'Joda-Money', 'Textr', 'Commons-CLI', 'Commons-CSV', 'Commons-Validator'}, ...
    {   334,          1495,      249,        977,           923,             992          } ...
);
% Set to 0 for projects where you don't know the suite size — they will be
% estimated as max(unique_tests_hit) across all probes for that project.
SAVE_FIGS = true;
BASE_DIR = '../';
if isempty(BASE_DIR), BASE_DIR = '.'; end

OUT_DIR = fullfile(BASE_DIR, 'analysis_results');
if SAVE_FIGS && ~exist(OUT_DIR, 'dir')
    mkdir(OUT_DIR);
end
% ── Colour palette ────────────────────────────────────────────────────────
C_CLEAN   = [0.45 0.75 0.45];   % soft green  — Clean Kill
C_DIRTY   = [0.95 0.80 0.25];   % soft yellow — Dirty Kill
C_SURVIVE = [0.85 0.35 0.35];   % soft red    — Survived
C_UNHIT   = [0.72 0.72 0.72];   % grey        — Un-hit
C_TIMEOUT = [0.55 0.35 0.65];   % purple      — Timed Out

OUTCOME_COLORS = [C_CLEAN; C_DIRTY; C_SURVIVE; C_UNHIT; C_TIMEOUT];
OUTCOME_LABELS = {'Clean Kill','Dirty Kill','Survived','Un-hit','Timed Out'};
OUTCOME_ORDER  = {'Clean Kill','Dirty Kill','Survived','Un-hit','Timed Out'};

set(0,'DefaultAxesFontName','Helvetica','DefaultAxesFontSize',11);
set(0,'DefaultTextFontName','Helvetica');
FIG_W = 1020; FIG_H = 540;

% =========================================================================
%% 0.  Load & parse database
% =========================================================================
fprintf('Loading %s ...\n', DB_PATH);
raw = jsondecode(fileread(DB_PATH));

probes     = raw.probes;
test_execs = raw.test_executions;

probe_projects  = {probes.project};
probe_outcomes_raw = {probes.probe_outcome};
probe_timed_out    = [probes.timed_out];
% Override outcome to 'Timed Out' where the timed_out flag is set,
% regardless of what probe_outcome says (it would have been 'Dirty Kill').
probe_outcomes = probe_outcomes_raw;
for ii = 1:numel(probe_outcomes)
    if probe_timed_out(ii)
        probe_outcomes{ii} = 'Timed Out';
    end
end
clear probe_outcomes_raw ii;
probe_operators = {probes.operator};
probe_hits        = [probes.total_hits];
probe_unique_hits = [probes.unique_tests_hit];

projects = unique(probe_projects, 'stable');
nP       = numel(projects);

fprintf('Loaded %d probes across %d project(s).\n', numel(probes), nP);

% =========================================================================
%% Shared helpers
% =========================================================================

function save_fig(fig, out_dir, name)
    png_name = fullfile(out_dir, [name '.png']);
    exportgraphics(fig, png_name, 'Resolution', 300);
    
    pdf_name = fullfile(out_dir, [name '.pdf']);
    exportgraphics(fig, pdf_name, 'ContentType', 'vector', 'BackgroundColor', 'none');
    
    fprintf('  Saved: %s (.png & .pdf)\n', name);
end

% nGroups×4 percentage matrix + absolute counts + row totals
function [pct, abs_c, totals] = outcome_matrix(group_var, outcomes, group_list, order)
    nG    = numel(group_list);
    nK    = numel(order);
    abs_c = zeros(nG, nK);
    for i = 1:nG
        mask = strcmp(group_var, group_list{i});
        for k = 1:nK
            abs_c(i,k) = sum(strcmp(outcomes(mask), order{k}));
        end
    end
    totals = sum(abs_c, 2);
    pct    = abs_c ./ max(totals,1) * 100;
end

% Draw 100% stacked bar with n= labels and inside % labels
function draw_stacked(ax, pct, totals, x_labels, colors, leg_labels, min_pct)
    nG = size(pct,1);
    nK = size(colors,1);
    b  = bar(ax, pct, 'stacked', 'BarWidth', 0.6);
    for k = 1:nK
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
    for k = 1:nK
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
%% Fig 1 — Probe outcome per project + aggregated  (perfect — unchanged)
% =========================================================================
fprintf('\nFig 1: Probe outcome per project + aggregated ...\n');

[pct1, abs1, tot1] = outcome_matrix(probe_projects, probe_outcomes, projects, OUTCOME_ORDER);

agg_abs = sum(abs1,1);  agg_tot = sum(agg_abs);
agg_pct = agg_abs / agg_tot * 100;

pct_f1  = [pct1;  agg_pct];
tot_f1  = [tot1;  agg_tot];
labs_f1 = [projects, {'All Projects'}];

fig1 = figure('Position',[100 100 FIG_W FIG_H], 'Color','w');
ax1  = axes(fig1);
draw_stacked(ax1, pct_f1, tot_f1, labs_f1, OUTCOME_COLORS, OUTCOME_LABELS, 5);
xline(ax1, nP+0.5, '--', 'Color',[0.6 0.6 0.6], 'LineWidth',1.2, 'Alpha',0.6, 'HandleVisibility','off');
ax1.Title.String     = 'Probe Outcome Distribution — Per Project & Overall';
ax1.Title.FontWeight = 'bold';

if SAVE_FIGS, save_fig(fig1, OUT_DIR, 'fig1_outcome_per_project'); end

% =========================================================================
%% Fig 2 — Probe outcome by operator type aggregated  (perfect — unchanged)
% =========================================================================
fprintf('Fig 2: Probe outcome by operator aggregated ...\n');

exec_mask = ~strcmp(probe_outcomes,'Un-hit') & ~strcmp(probe_outcomes,'Timed Out');
all_ops   = sort(unique(probe_operators(exec_mask)));
nOps      = numel(all_ops);

[pct2, ~, tot2] = outcome_matrix(probe_operators(exec_mask), probe_outcomes(exec_mask), ...
                                  all_ops, OUTCOME_ORDER);
[~, si2] = sort(pct2(:,1),'descend');
pct2 = pct2(si2,:);  tot2 = tot2(si2);  ops2 = all_ops(si2);

fig2 = figure('Position',[100 100 max(FIG_W, nOps*130+220) FIG_H], 'Color','w');
ax2  = axes(fig2);
draw_stacked(ax2, pct2(:,1:3), tot2, ops2, OUTCOME_COLORS(1:3,:), OUTCOME_LABELS(1:3), 5);
ax2.Title.String     = 'Probe Outcome by Operator Type — Aggregated (sorted by Clean Kill %)';
ax2.Title.FontWeight = 'bold';

if SAVE_FIGS, save_fig(fig2, OUT_DIR, 'fig2_outcome_by_operator'); end

% =========================================================================
%% Fig 3 — CLEAN kill-rate heatmap: projects (rows) × operator types (cols)
%  Cells show CLEAN kill rate only (assertion failures) — not dirty kills.
%  This is a stricter quality metric: it measures how well the test suite
%  catches perturbations through deliberate assertions rather than crashes.
%  White = 0% clean kills (operator goes undetected by assertions),
%  deep teal = 100%. n= shows executed probe count per cell.
% =========================================================================
fprintf('Fig 3: Clean kill-rate heatmap (projects x operators) ...\n');

ck_heat = NaN(nP, nOps);   % CLEAN kill rate per cell
n_heat  = zeros(nP, nOps);

for i = 1:nP
    for j = 1:nOps
        m = strcmp(probe_projects, projects{i}) & ...
            strcmp(probe_operators, all_ops{j}) & exec_mask;
        n_heat(i,j) = sum(m);
        if n_heat(i,j) == 0, continue; end
        clean_killed = m & strcmp(probe_outcomes,'Clean Kill');
        ck_heat(i,j) = sum(clean_killed) / n_heat(i,j) * 100;
    end
end

% Sort operators by mean clean kill rate descending
mean_ck = mean(ck_heat, 1, 'omitnan');
[~, op_sort] = sort(mean_ck,'descend');
ck_plot  = ck_heat(:, op_sort);
n_plot   = n_heat(:,  op_sort);
ops_plot = all_ops(op_sort);

fig3 = figure('Position',[100 100 max(700, nOps*95+180) max(320, nP*80+180)], 'Color','w');
ax3  = axes(fig3);

% White → teal colormap
cmap3 = interp1([0;0.5;1], [1 1 1; 0.55 0.85 0.82; 0.10 0.50 0.55], linspace(0,1,256));
colormap(ax3, cmap3);

img3 = ck_plot / 100;
imagesc(ax3, img3, [0 1]);

ax3.XTick              = 1:nOps;
ax3.XTickLabel         = ops_plot;
ax3.XTickLabelRotation = 30;
ax3.YTick              = 1:nP;
ax3.YTickLabel         = projects;
ax3.TickLength         = [0 0];
ax3.Box                = 'off';
ax3.Title.String       = 'Clean Kill Rate Heatmap — Projects × Operator Types (executed probes only)';
ax3.Title.FontWeight   = 'bold';

cb3 = colorbar(ax3);
cb3.Label.String = 'Clean kill rate (%)';
cb3.Ticks        = 0:0.25:1;
cb3.TickLabels   = {'0%','25%','50%','75%','100%'};

for i = 1:nP
    for j = 1:nOps
        if isnan(ck_plot(i,j))
            text(ax3, j, i, 'n/a', 'HorizontalAlignment','center', ...
                 'FontSize',8,'Color',[0.65 0.65 0.65]);
        else
            txt_col = [1 1 1] * double(ck_plot(i,j) < 55);
            text(ax3, j, i-0.15, sprintf('%.0f%%', ck_plot(i,j)), ...
                 'HorizontalAlignment','center','FontSize',9, ...
                 'FontWeight','bold','Color',txt_col);
            n_col = txt_col * 0.8 + [0.2 0.2 0.2] * (1 - double(ck_plot(i,j) < 55));
            text(ax3, j, i+0.22, sprintf('n=%d', n_plot(i,j)), ...
                 'HorizontalAlignment','center','FontSize',7.5,'Color',n_col);
        end
    end
end

if SAVE_FIGS, save_fig(fig3, OUT_DIR, 'fig3_cleankill_heatmap'); end

% =========================================================================
%% Fig 4 — Unique probes vs total hits, per project + average across projects
%  Left bar  = number of unique probes (scale of instrumentation).
%  Right bar = total hits (all tests × all probes).
%  The "All Projects" bar shows the AVERAGE per-project values (not the sum),
%  so it stays on the same scale as the individual project bars and is
%  directly comparable — no single large project can dominate.
%  ×N multiplier = total_hits / unique_probes for each project.
% =========================================================================
fprintf('Fig 4: Unique probes vs total hits per project + avg ...\n');

n_unique  = zeros(nP,1);
n_hits    = zeros(nP,1);
for i = 1:nP
    mask        = strcmp(probe_projects, projects{i});
    n_unique(i) = sum(mask);
    n_hits(i)   = sum(probe_hits(mask));
end

% "All Projects" = per-project averages so scale stays comparable
n_unique_all = [n_unique;  mean(n_unique)];
n_hits_all   = [n_hits;    mean(n_hits)  ];
labs4        = [projects,  {'Avg (all projects)'}];
nBars4       = nP + 1;

fig4 = figure('Position',[100 100 FIG_W FIG_H], 'Color','w');
ax4  = axes(fig4);

b4 = bar(ax4, [n_unique_all, n_hits_all], 'grouped', 'BarWidth',0.6);
b4(1).FaceColor = [0.40 0.62 0.82]; b4(1).EdgeColor = 'none';
b4(2).FaceColor = [0.85 0.55 0.35]; b4(2).EdgeColor = 'none';

xline(ax4, nP+0.5, '--', 'Color',[0.6 0.6 0.6], 'LineWidth',1.2, 'Alpha',0.6);

ax4.XTick              = 1:nBars4;
ax4.XTickLabel         = labs4;
ax4.XTickLabelRotation = 20;
ax4.YLabel.String      = 'Count';
ax4.Title.String       = 'Unique Probes vs Total Test Hits — Per Project & Average';
ax4.Title.FontWeight   = 'bold';
ax4.Box                = 'off';
ax4.YGrid              = 'on';
ax4.GridAlpha          = 0.15;
legend(ax4, {'Unique probes','Total hits (summed across all tests)'}, ...
       'Location','northeastoutside','Box','off','FontSize',10);

bw4 = 0.6/3;
yc4 = ax4.YLim(2);
for i = 1:nBars4
    ratio = n_hits_all(i) / max(n_unique_all(i),1);
    text(ax4, i+bw4, n_hits_all(i)+yc4*0.018, sprintf('×%.1f',ratio), ...
         'HorizontalAlignment','center','FontSize',9.5, ...
         'Color',[0.55 0.22 0.05],'FontWeight','bold');
    text(ax4, i-bw4, n_unique_all(i)+yc4*0.018, sprintf('%d',round(n_unique_all(i))), ...
         'HorizontalAlignment','center','FontSize',8,'Color',[0.18 0.34 0.54]);
end

if SAVE_FIGS, save_fig(fig4, OUT_DIR, 'fig4_hits_vs_probes'); end

% =========================================================================
%% Fig 5 — Exception type frequency  (perfect — unchanged)
% =========================================================================
fprintf('Fig 5: Exception type frequency ...\n');

exec_outcomes = {test_execs.test_outcome};
exec_excs     = {test_execs.exception};
dirty_mask_te = strcmp(exec_outcomes,'FAIL by Exception');
dirty_excs    = exec_excs(dirty_mask_te);
dirty_excs    = dirty_excs(~strcmp(dirty_excs,'none') & ~strcmp(dirty_excs,'Unknown'));

if isempty(dirty_excs)
    fprintf('  No dirty-kill exceptions — skipping Fig 5.\n');
else
    [exc_names,~,ic] = unique(dirty_excs);
    exc_counts = accumarray(ic,1);
    [exc_c_s, si5] = sort(exc_counts,'descend');
    exc_n_s  = exc_names(si5);
    top_n    = min(15, numel(exc_n_s));
    exc_c_s  = exc_c_s(1:top_n);
    exc_n_s  = exc_n_s(1:top_n);

    fig5 = figure('Position',[100 100 FIG_W max(FIG_H, top_n*42+120)], 'Color','w');
    ax5  = axes(fig5);
    barh(ax5, exc_c_s, 'FaceColor',C_DIRTY, 'EdgeColor','none', 'BarWidth',0.65);
    ax5.YTick         = 1:top_n;
    ax5.YTickLabel    = exc_n_s;
    ax5.XLabel.String = 'Frequency (test executions)';
    ax5.Title.String  = 'Exception Types in Dirty-Kill Test Executions';
    ax5.Title.FontWeight = 'bold';
    ax5.Box           = 'off';
    ax5.XGrid         = 'on';
    ax5.GridAlpha     = 0.15;
    ax5.YDir          = 'reverse';

    tot5 = sum(exc_c_s);
    for j = 1:top_n
        text(ax5, exc_c_s(j)+max(exc_c_s)*0.012, j, ...
             sprintf('%d  (%.1f%%)', exc_c_s(j), exc_c_s(j)/tot5*100), ...
             'VerticalAlignment','middle','FontSize',9,'Color',[0.3 0.3 0.3]);
    end
    ax5.XLim(2) = max(exc_c_s)*1.30;

    if SAVE_FIGS, save_fig(fig5, OUT_DIR, 'fig5_exception_frequency'); end
end

% =========================================================================
%% Fig 6 — Hit-count rank scatter per project  (small multiples)
%  X axis: probe rank (1 = most-hit probe, N = least-hit probe).
%  Y axis: hit count (log scale). Each dot = one probe, coloured by outcome.
%  A steep early drop = a few hotspot probes dominate all test activity;
%  a flatter curve = coverage is more evenly spread.
%  Dotted line at y=1 marks the boundary of probes hit by exactly one test.
% =========================================================================
fprintf('Fig 6: Hit-count rank scatter per project ...\n');

oc_colors = {C_CLEAN, C_DIRTY, C_SURVIVE, C_UNHIT, C_TIMEOUT};   % matches OUTCOME_ORDER

ncols6 = min(nP,3);
nrows6 = ceil(nP/ncols6);
fig6   = figure('Position',[100 100 ncols6*390 nrows6*320], 'Color','w');

last_ax6 = [];
for i = 1:nP
    mask     = strcmp(probe_projects, projects{i});
    h_proj   = probe_hits(mask);
    out_proj = probe_outcomes(mask);

    [h_sorted, sort_idx] = sort(h_proj, 'descend');
    out_sorted = out_proj(sort_idx);
    ranks      = 1:numel(h_sorted);

    ax6 = subplot(nrows6, ncols6, i);
    hold(ax6,'on');

    for k = 1:numel(OUTCOME_ORDER)
        sel = strcmp(out_sorted, OUTCOME_ORDER{k});
        if any(sel)
            scatter(ax6, ranks(sel), h_sorted(sel)+0.5, 14, ...
                    oc_colors{k}, 'filled', 'MarkerFaceAlpha',0.60, ...
                    'DisplayName', OUTCOME_LABELS{k});
        end
    end

    yline(ax6, 1.5, ':', 'Color',[0.55 0.55 0.55], 'LineWidth',1.1, ...
          'HandleVisibility','off');

    ax6.YScale           = 'log';
    ax6.Title.String     = projects{i};
    ax6.Title.FontWeight = 'bold';
    ax6.XLabel.String    = 'Probe rank (sorted by hits descending)';
    ax6.YLabel.String    = 'Hit count (log)';
    ax6.Box              = 'off';
    ax6.YGrid            = 'on';
    ax6.XGrid            = 'on';
    ax6.GridAlpha        = 0.12;

    n_total = numel(h_sorted);
    n_exec  = sum(h_sorted > 0);
    text(ax6, n_total*0.03, ax6.YLim(1)*1.8, ...
         sprintf('n=%d  |  %d executed', n_total, n_exec), ...
         'HorizontalAlignment','left','FontSize',7.5,'Color',[0.4 0.4 0.4]);
    hold(ax6,'off');
    last_ax6 = ax6;
end

legend(last_ax6, 'Location','southeast','Box','off','FontSize',9);
sgtitle(fig6, 'Probe Hit-Count Rank — per Project  (steep drop = hotspot-dominated coverage)', ...
        'FontWeight','bold','FontSize',12);

if SAVE_FIGS, save_fig(fig6, OUT_DIR, 'fig6_rank_scatter_per_project'); end

% =========================================================================
%% Fig 7 — Hit-count rank scatter AGGREGATED (Stacked with Smooth Trends)
%  All probes from all projects on one single plot, same axes as Fig 6.
%  X axis: probe rank across all projects combined (1 = globally most-hit).
%  Y axis: hit count (log scale). Dots coloured by outcome.
%  This is the "master Zipf curve" — shows how quickly hit counts fall off
%  across the entire benchmark suite, with the outcome mix overlaid.
% =========================================================================

fprintf('Fig 7: Hit-count rank scatter aggregated (stacked) ...\n');

[h_all_s, all_sort_idx] = sort(probe_hits, 'descend');
out_all_s  = probe_outcomes(all_sort_idx);
n_all      = numel(h_all_s);
ranks_all  = 1:n_all;

% Make the figure slightly taller to comfortably fit both plots
fig7 = figure('Position',[100 100 FIG_W FIG_H+120], 'Color','w');

% --- TOP PLOT: The Standard Scatter Plot (Takes up top 3/4 of the figure) ---
ax7_top = subplot(4, 1, [1 2 3]);
hold(ax7_top, 'on');

for k = 1:numel(OUTCOME_ORDER)
    sel = strcmp(out_all_s, OUTCOME_ORDER{k});
    if any(sel)
        scatter(ax7_top, ranks_all(sel), h_all_s(sel)+0.5, 20, ...
                oc_colors{k}, 'filled', 'MarkerFaceAlpha', 0.50, ...
                'DisplayName', OUTCOME_LABELS{k});
    end
end

yline(ax7_top, 1.5, ':', 'Color',[0.55 0.55 0.55], 'LineWidth',1.1, ...
      'HandleVisibility','off');

ax7_top.YScale        = 'log';
ax7_top.YLabel.String = 'Hit count (log)';
ax7_top.Title.String  = 'Probe Hit-Count Rank & Outcome Probabilities — All Projects Combined';
ax7_top.Title.FontWeight = 'bold';
ax7_top.Box           = 'off';
ax7_top.YGrid         = 'on'; 
ax7_top.XGrid         = 'on'; 
ax7_top.GridAlpha     = 0.12;
% Hide X-axis labels on top plot so it flows cleanly into the bottom plot
ax7_top.XTickLabel    = []; 

legend(ax7_top, 'Location', 'northeast', 'Box', 'off', 'FontSize', 10);

n_exec_all = sum(h_all_s > 0);
text(ax7_top, n_all*0.03, ax7_top.YLim(2)*0.40, ...
     sprintf('n=%d probes\n%d executed', n_all, n_exec_all), ...
     'HorizontalAlignment','left','FontSize',9,'Color',[0.4 0.4 0.4]);
hold(ax7_top, 'off');


% --- BOTTOM PLOT: Narrow Subplot for Smooth Trendlines ---
ax7_bot = subplot(4, 1, 4);
hold(ax7_bot, 'on');

% Extract binary arrays for outcomes (Added Dirty Kill)
is_clean   = double(strcmp(out_all_s, 'Clean Kill')) * 100;
is_dirty   = double(strcmp(out_all_s, 'Dirty Kill')) * 100;
is_survive = double(strcmp(out_all_s, 'Survived')) * 100;

% Use a Gaussian window for an ultra-smooth, sweeping curve
window_size = max(50, round(n_all * 0.40));
smooth_clean   = smoothdata(is_clean, 'gaussian', window_size);
smooth_dirty   = smoothdata(is_dirty, 'gaussian', window_size);
smooth_survive = smoothdata(is_survive, 'gaussian', window_size);

% Plot the smooth lines (Added the Dirty Kill plot)
plot(ax7_bot, ranks_all, smooth_clean, '-', 'LineWidth', 2.5, ...
     'Color', oc_colors{1}, 'DisplayName', 'Clean Kill %');
plot(ax7_bot, ranks_all, smooth_dirty, '-', 'LineWidth', 2.5, ...
     'Color', oc_colors{2}, 'DisplayName', 'Dirty Kill %');
plot(ax7_bot, ranks_all, smooth_survive, '-', 'LineWidth', 2.5, ...
     'Color', oc_colors{3}, 'DisplayName', 'Survived %');

ax7_bot.YLim          = [0 100];
ax7_bot.XLabel.String = 'Probe rank across all projects (sorted by hits descending)';
ax7_bot.YLabel.String = 'Likelihood (%)';
ax7_bot.Box           = 'off';
ax7_bot.YGrid         = 'on'; 
ax7_bot.XGrid         = 'on'; 
ax7_bot.GridAlpha     = 0.12;
legend(ax7_bot, 'Location', 'eastoutside', 'Box', 'off', 'FontSize', 9);

% Link the X-axes so zooming/panning perfectly aligns both graphs
linkaxes([ax7_top, ax7_bot], 'x');
ax7_top.XLim = [1, n_all]; % Snap to edge

hold(ax7_bot, 'off');

if SAVE_FIGS, save_fig(fig7, OUT_DIR, 'fig7_rank_scatter_aggregated'); end

% =========================================================================
%% Fig 8 — Test execution efficiency: full suite vs actual tests run per probe
%
%  The tool's core optimisation is that during the discovery run it records
%  which tests actually reach each probe. When evaluating a probe, only those
%  tests are re-run — not the full suite. This figure makes that saving
%  concrete and comparable across projects.
%
%  For each project, three values are shown:
%    Full suite size  — total tests that exist in the project
%    Mean tests/probe — average number of tests re-run per probe evaluation
%    Median tests/probe — median (more robust to hotspot outliers)
%
%  The gap between the blue bar and the orange/yellow bars IS the optimisation:
%  it represents the tests that were skipped because the discovery run proved
%  they never reach that probe. A large gap = high efficiency gain.
% =========================================================================
fprintf('\nFig 8: Test execution efficiency ...');

suite_sizes  = zeros(nP,1);
mean_tests   = zeros(nP,1);
median_tests = zeros(nP,1);
pct_saved    = zeros(nP,1);

for i = 1:nP
    mask = strcmp(probe_projects, projects{i});

    % Full suite size: use configured value if available, else estimate
    if isKey(FULL_SUITE_SIZES, projects{i}) && FULL_SUITE_SIZES(projects{i}) > 0
        suite_sizes(i) = FULL_SUITE_SIZES(projects{i});
    else
        % Fallback: max unique_tests_hit seen for any probe in this project
        suite_sizes(i) = max(probe_unique_hits(mask));
        fprintf('  [%s] suite size not configured — estimated as %d\n', ...
                projects{i}, suite_sizes(i));
    end

    % Only executed probes (probes with at least 1 hit)
    hits_proj = probe_unique_hits(mask);
    executed  = hits_proj(hits_proj > 0);
    if isempty(executed)
        mean_tests(i)   = 0;
        median_tests(i) = 0;
    else
        mean_tests(i)   = mean(executed);
        median_tests(i) = median(executed);
    end

    pct_saved(i) = (1 - mean_tests(i) / max(suite_sizes(i),1)) * 100;
end

% Append aggregate bar (averages across projects)
suite_all  = [suite_sizes;  mean(suite_sizes)];
mean_all   = [mean_tests;   mean(mean_tests)];
median_all = [median_tests; mean(median_tests)];
labs8      = [projects, {'Avg (all)'}];
nBars8     = nP + 1;

fig8 = figure('Position',[100 100 FIG_W FIG_H], 'Color','w');
ax8  = axes(fig8);

b8 = bar(ax8, [suite_all, mean_all, median_all], 'grouped', 'BarWidth',0.72);
b8(1).FaceColor = [0.40 0.62 0.82]; b8(1).EdgeColor = 'none';  % blue  — full suite
b8(2).FaceColor = [0.85 0.55 0.35]; b8(2).EdgeColor = 'none';  % orange — mean
b8(3).FaceColor = [0.95 0.80 0.25]; b8(3).EdgeColor = 'none';  % yellow — median

xline(ax8, nP+0.5, '--', 'Color',[0.6 0.6 0.6], 'LineWidth',1.2, 'Alpha',0.6);

ax8.XTick              = 1:nBars8;
ax8.XTickLabel         = labs8;
ax8.XTickLabelRotation = 20;
ax8.YLabel.String      = 'Number of tests';
ax8.Title.String       = 'Test Execution Efficiency — Full Suite vs Tests Actually Run per Probe';
ax8.Title.FontWeight   = 'bold';
ax8.TitleFontSizeMultiplier = 1.0;
ax8.Position(4) = ax8.Position(4) - 0.04;   % shrink axes height slightly to give title room
ax8.Position(2) = ax8.Position(2) + 0.04;   % shift axes up to compensate
ax8.Box                = 'off';
ax8.YGrid              = 'on';
ax8.GridAlpha          = 0.15;
legend(ax8, {'Full suite size', 'Mean tests run per probe', 'Median tests run per probe'}, ...
       'Location','northeastoutside','Box','off','FontSize',10);

% Annotate: % saved above the full-suite bar, counts above the other bars
bw8 = 0.72 / 4;
yc8 = ax8.YLim(2);
for i = 1:nBars8
    % Full suite bar: show % saved
    if suite_all(i) > 0
        if i <= nP
            saved_pct = (1 - mean_all(i)/suite_all(i)) * 100;
        else
            saved_pct = mean(pct_saved);
        end
        text(ax8, i - bw8, suite_all(i) + yc8*0.018, ...
             sprintf('%.0f%% skipped', saved_pct), ...
             'HorizontalAlignment','center','FontSize',8, ...
             'Color',[0.18 0.34 0.54],'FontWeight','bold');
    end
    % Mean bar: show value
    text(ax8, i, mean_all(i) + yc8*0.018, sprintf('%.0f', mean_all(i)), ...
         'HorizontalAlignment','center','FontSize',8,'Color',[0.50 0.28 0.10]);
    % Median bar: show value
    text(ax8, i + bw8, median_all(i) + yc8*0.018, sprintf('%.0f', median_all(i)), ...
         'HorizontalAlignment','center','FontSize',8,'Color',[0.55 0.48 0.05]);
end

if SAVE_FIGS, save_fig(fig8, OUT_DIR, 'fig8_test_efficiency'); end

% =========================================================================
%% Fig 9 — Per-probe test reduction distribution
%
%  For every executed probe, compute what fraction of the full test suite
%  was actually needed: unique_tests_hit / suite_size * 100.
%  Plotted as a histogram per project (small multiples).
%
%  Most probes will cluster near 0% — meaning the tool only needs to run
%  a tiny fraction of the suite for that probe. A small number of "hotspot"
%  probes may require a larger fraction. This directly visualises the
%  distribution of the efficiency gain across all probes.
% =========================================================================
fprintf('Fig 9: Per-probe test reduction distribution ...');

ncols9 = min(nP,3);
nrows9 = ceil(nP/ncols9);
fig9   = figure('Position',[100 100 ncols9*360 nrows9*300], 'Color','w');

for i = 1:nP
    mask     = strcmp(probe_projects, projects{i});
    u_hits   = probe_unique_hits(mask);
    u_hits   = u_hits(u_hits > 0);   % executed probes only
    ss       = suite_sizes(i);

    ax9 = subplot(nrows9, ncols9, i);
    if isempty(u_hits) || ss == 0
        text(0.5,0.5,'No data','HorizontalAlignment','center'); continue;
    end

    pct_needed = u_hits / ss * 100;

    % Fixed edges 0-100% in steps of 5
    edges9 = 0:5:100;
    histogram(ax9, min(pct_needed,100), edges9, ...
              'FaceColor',[0.40 0.62 0.82], 'EdgeColor','w', 'FaceAlpha',0.88);

    % Mark the mean and median
    xline(ax9, mean(pct_needed),   '--', 'Color', C_SURVIVE,      'LineWidth',1.6, ...
          'Label', sprintf('mean=%.0f%%', mean(pct_needed)), ...
          'LabelVerticalAlignment','bottom','FontSize',8);
    xline(ax9, median(pct_needed), ':',  'Color', [0.15 0.15 0.15], 'LineWidth',1.6, ...
          'Label', sprintf('med=%.0f%%', median(pct_needed)), ...
          'LabelVerticalAlignment','top','FontSize',8);

    ax9.XLim             = [0 100];
    ax9.XLabel.String    = '% of full test suite needed';
    ax9.YLabel.String    = 'Number of probes';
    ax9.Title.String     = projects{i};
    ax9.Title.FontWeight = 'bold';
    ax9.Box              = 'off';
    ax9.YGrid            = 'on'; ax9.GridAlpha = 0.15;

    % Annotation: n probes, suite size used
    text(ax9, 98, ax9.YLim(2)*0.95, ...
         sprintf('n=%d probes\nsuite=%d tests', numel(u_hits), ss), ...
         'HorizontalAlignment','right','FontSize',8,'Color',[0.4 0.4 0.4]);
end

sgtitle(fig9, 'Per-Probe Test Reduction — what fraction of the full suite does each probe actually need?', ...
        'FontWeight','bold','FontSize',12);

if SAVE_FIGS, save_fig(fig9, OUT_DIR, 'fig9_test_reduction'); end

% =========================================================================
fprintf('\nDone. All figures generated.\n');
if SAVE_FIGS, fprintf('PNGs saved to: %s\n', OUT_DIR); end