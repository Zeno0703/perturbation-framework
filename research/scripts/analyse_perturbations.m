clear; clc; close all;

%% --- Configuration ---
DB_PATH = '../data/database.json';
FULL_SUITE_SIZES = containers.Map( ...
    {'JSemVer', 'Joda-Money', 'Joda-Beans', 'Joda-Convert', 'Commons-CLI', 'Commons-CSV', 'Commons-Validator'}, ...
    {334, 1495, 1226, 198, 977, 923, 992} ...
);
SAVE_FIGS = false;
BASE_DIR = '../';
OUT_DIR = fullfile(BASE_DIR, 'analysis_results');
if SAVE_FIGS && ~exist(OUT_DIR, 'dir')
    mkdir(OUT_DIR);
end

C_CLEAN   = [0.45 0.75 0.45];
C_DIRTY   = [0.95 0.80 0.25];
C_SURVIVE = [0.85 0.35 0.35];
C_UNHIT   = [0.72 0.72 0.72];
C_TIMEOUT = [0.55 0.35 0.65];

OUTCOME_COLORS = [C_CLEAN; C_DIRTY; C_SURVIVE; C_UNHIT; C_TIMEOUT];
OUTCOME_LABELS = {'Clean Kill','Dirty Kill','Survived','Un-hit','Timed Out'};
OUTCOME_ORDER  = {'Clean Kill','Dirty Kill','Survived','Un-hit','Timed Out'};

set(0,'DefaultAxesFontName','Helvetica','DefaultAxesFontSize',11);
set(0,'DefaultTextFontName','Helvetica');
FIG_W = 1020; FIG_H = 540;

%% --- Load & Parse Database ---
fprintf('Loading %s ...\n', DB_PATH);
raw = jsondecode(fileread(DB_PATH));

probes = raw.probes;
test_execs = raw.test_executions;

probe_projects = {probes.project};
probe_outcomes_raw = {probes.probe_outcome};
probe_timed_out = [probes.timed_out];

% Override outcome to 'Timed Out' where flag is set
probe_outcomes = probe_outcomes_raw;
for ii = 1:numel(probe_outcomes)
    if probe_timed_out(ii)
        probe_outcomes{ii} = 'Timed Out';
    end
end
clear probe_outcomes_raw ii;

probe_operators = {probes.operator};
probe_hits = [probes.total_hits];
probe_unique_hits = [probes.unique_tests_hit];

projects = unique(probe_projects, 'stable');
nP = numel(projects);
proj_cmap = lines(nP);

%% --- Figure 1: Probe outcome per project + aggregated ---
fprintf('Generating Fig 1...\n');
[pct1, abs1, tot1] = outcome_matrix(probe_projects, probe_outcomes, projects, OUTCOME_ORDER);

agg_abs = sum(abs1,1);  
agg_tot = sum(agg_abs);
agg_pct = agg_abs / agg_tot * 100;

pct_f1  = [pct1; agg_pct];
tot_f1  = [tot1; agg_tot];
labs_f1 = [projects, {'All Projects'}];

fig1 = figure('Position',[100 100 FIG_W FIG_H], 'Color','w');
ax1  = axes(fig1);
draw_stacked(ax1, pct_f1, tot_f1, labs_f1, OUTCOME_COLORS, OUTCOME_LABELS, 5);
xline(ax1, nP+0.5, '--', 'Color',[0.6 0.6 0.6], 'LineWidth',1.2, 'Alpha',0.6, 'HandleVisibility','off');
ax1.Title.String = 'Probe Outcome Distribution — Per Project & Overall';
ax1.Title.FontWeight = 'bold';

if SAVE_FIGS, save_fig(fig1, OUT_DIR, 'fig1_outcome_per_project'); end

%% --- Figure 2: Test-execution outcome distribution per project ---
fprintf('Generating Fig 2...\n');
% Each row in test_executions is one probe×test pair execution.
% We categorise each execution using the same colour scheme as Fig 1,
% mapping test_outcome / exception fields onto our 6-slot legend.
%
%   FAIL by Assert   -> Clean Kill  (C_CLEAN)
%   FAIL by Exception (non-timeout) -> Dirty Kill  (C_DIRTY)
%   PASS             -> Survived    (C_SURVIVE)
%   FAIL by Exception (timeout)     -> Timed Out   (C_TIMEOUT)
%   Un-hit (probe never reached)    -> Un-hit      (C_UNHIT)
%   UNREACHED / other               -> Unreached   (new grey-blue)

C_UNREACH = [0.55 0.65 0.75];   % grey-blue for unreached executions

TEST_OUTCOME_ORDER  = {'Clean Kill','Dirty Kill','Survived','Timed Out','Un-hit','Unreached'};
TEST_OUTCOME_COLORS = [C_CLEAN; C_DIRTY; C_SURVIVE; C_TIMEOUT; C_UNHIT; C_UNREACH];
TEST_OUTCOME_LABELS = {'Failed by Assert','Failed by Exception','Passed','Timed Out','Un-hit','Unreached'};

exec_proj_all  = {test_execs.project};
exec_outcomes_all = {test_execs.test_outcome};
exec_excs_all  = {test_execs.exception};

% Map each test_execution row to one of the 6 categories
n_te = numel(test_execs);
te_cat = cell(n_te, 1);
for ii = 1:n_te
    oc  = exec_outcomes_all{ii};
    exc = exec_excs_all{ii};
    if strcmp(oc, 'FAIL by Assert')
        te_cat{ii} = 'Clean Kill';
    elseif strcmp(oc, 'FAIL by Exception')
        if strcmp(exc,'JVM-Timeout') || strcmp(exc,'TIMEOUT')
            te_cat{ii} = 'Timed Out';
        else
            te_cat{ii} = 'Dirty Kill';
        end
    elseif strcmp(oc, 'PASS')
        te_cat{ii} = 'Survived';
    elseif contains(lower(oc), 'unreached') || contains(lower(oc), 'aborted') || contains(lower(oc), 'skipped')
        te_cat{ii} = 'Unreached';
    elseif contains(lower(oc), 'un-hit') || contains(lower(oc), 'unhit')
        te_cat{ii} = 'Un-hit';
    else
        te_cat{ii} = 'Unreached';   % catch-all
    end
end

% Build per-project and aggregate counts
[pct2_te, abs2_te, tot2_te] = outcome_matrix(exec_proj_all, te_cat, projects, TEST_OUTCOME_ORDER);

agg2_abs = sum(abs2_te, 1);
agg2_tot = sum(agg2_abs);
agg2_pct = agg2_abs / max(agg2_tot,1) * 100;

pct_f2  = [pct2_te; agg2_pct];
tot_f2  = [tot2_te; agg2_tot];
labs_f2 = [projects, {'All Projects'}];

fig2 = figure('Position',[100 100 FIG_W FIG_H], 'Color','w');
ax2  = axes(fig2);
draw_stacked(ax2, pct_f2, tot_f2, labs_f2, TEST_OUTCOME_COLORS, TEST_OUTCOME_LABELS, 5);
xline(ax2, nP+0.5, '--', 'Color',[0.6 0.6 0.6], 'LineWidth',1.2, 'Alpha',0.6, 'HandleVisibility','off');
ax2.Title.String = 'Test-Execution Outcome Distribution — Per Project & Overall';
ax2.Title.FontWeight = 'bold';

if SAVE_FIGS, save_fig(fig2, OUT_DIR, 'fig2_test_outcome_per_project'); end

%% --- Figure 3: Probe outcome by operator type aggregated ---
fprintf('Generating Fig 3...\n');
exec_mask = ~strcmp(probe_outcomes,'Un-hit') & ~strcmp(probe_outcomes,'Timed Out');
all_ops = sort(unique(probe_operators(exec_mask)));
nOps = numel(all_ops);

[pct2, ~, tot2] = outcome_matrix(probe_operators(exec_mask), probe_outcomes(exec_mask), all_ops, OUTCOME_ORDER);
[~, si2] = sort(pct2(:,1),'descend');
pct2 = pct2(si2,:);  
tot2 = tot2(si2);  
ops2 = all_ops(si2);

fig3 = figure('Position',[100 100 max(FIG_W, nOps*130+220) FIG_H], 'Color','w');
ax3  = axes(fig3);
draw_stacked(ax3, pct2(:,1:3), tot2, ops2, OUTCOME_COLORS(1:3,:), OUTCOME_LABELS(1:3), 5);
ax3.Title.String = 'Probe Outcome by Operator Type — Aggregated';
ax3.Title.FontWeight = 'bold';

if SAVE_FIGS, save_fig(fig3, OUT_DIR, 'fig3_outcome_by_operator'); end

%% --- Figure 4: Unique probes vs total hits, per project + avg ---
fprintf('Generating Fig 4...\n');
n_unique = zeros(nP,1);
n_hits = zeros(nP,1);
for i = 1:nP
    mask = strcmp(probe_projects, projects{i});
    n_unique(i) = sum(mask);
    n_hits(i) = sum(probe_hits(mask));
end

n_unique_all = [n_unique; mean(n_unique)];
n_hits_all = [n_hits; mean(n_hits)];
labs3 = [projects, {'Avg (all projects)'}];
nBars3 = nP + 1;

fig4a = figure('Position',[100 100 FIG_W FIG_H], 'Color','w');
ax4a  = axes(fig4a);

b4a = bar(ax4a, [n_unique_all, n_hits_all], 'grouped', 'BarWidth',0.6);
b4a(1).FaceColor = [0.40 0.62 0.82]; b4a(1).EdgeColor = 'none';
b4a(2).FaceColor = [0.85 0.55 0.35]; b4a(2).EdgeColor = 'none';

xline(ax4a, nP+0.5, '--', 'Color',[0.6 0.6 0.6], 'LineWidth',1.2, 'Alpha',0.6);
ax4a.XTick = 1:nBars3;
ax4a.XTickLabel = labs3;
ax4a.XTickLabelRotation = 20;
ax4a.YLabel.String = 'Count';
ax4a.Title.String = 'Unique Probes vs Total Test Hits';
ax4a.Title.FontWeight = 'bold';
ax4a.Box = 'off';
ax4a.YGrid = 'on';
ax4a.GridAlpha = 0.15;
legend(ax4a, {'Unique probes','Total hits'}, 'Location','northeastoutside','Box','off');

bw3 = 0.6/3;
yc3 = ax4a.YLim(2);
for i = 1:nBars3
    ratio = n_hits_all(i) / max(n_unique_all(i),1);
    text(ax4a, i+bw3, n_hits_all(i)+yc3*0.018, sprintf('×%.1f',ratio), 'HorizontalAlignment','center','FontSize',9.5, 'Color',[0.55 0.22 0.05],'FontWeight','bold');
    text(ax4a, i-bw3, n_unique_all(i)+yc3*0.018, sprintf('%d',round(n_unique_all(i))), 'HorizontalAlignment','center','FontSize',8,'Color',[0.18 0.34 0.54]);
end

if SAVE_FIGS, save_fig(fig4a, OUT_DIR, 'fig4_hits_vs_probes'); end

%% --- Figure 5: Exception type frequency ---
fprintf('Generating Fig 5...\n');
exec_outcomes = {test_execs.test_outcome};
exec_excs = {test_execs.exception};
dirty_mask_te = strcmp(exec_outcomes,'FAIL by Exception');
dirty_excs = exec_excs(dirty_mask_te);
dirty_excs = dirty_excs(~strcmp(dirty_excs,'none') & ~strcmp(dirty_excs,'Unknown'));

if ~isempty(dirty_excs)
    [exc_names,~,ic] = unique(dirty_excs);
    exc_counts = accumarray(ic,1);
    [exc_c_s, si4] = sort(exc_counts,'descend');
    exc_n_s = exc_names(si4);
    top_n = min(15, numel(exc_n_s));
    exc_c_s = exc_c_s(1:top_n);
    exc_n_s = exc_n_s(1:top_n);

    fig5 = figure('Position',[100 100 FIG_W max(FIG_H, top_n*42+120)], 'Color','w');
    ax5  = axes(fig5);
    barh(ax5, exc_c_s, 'FaceColor',C_DIRTY, 'EdgeColor','none', 'BarWidth',0.65);
    ax5.YTick = 1:top_n;
    ax5.YTickLabel = exc_n_s;
    ax5.XLabel.String = 'Frequency';
    ax5.Title.String = 'Exception Types in Dirty-Kill Executions';
    ax5.Title.FontWeight = 'bold';
    ax5.Box = 'off';
    ax5.XGrid = 'on';
    ax5.GridAlpha = 0.15;
    ax5.YDir = 'reverse';

    tot5 = sum(exc_c_s);
    for j = 1:top_n
        text(ax5, exc_c_s(j)+max(exc_c_s)*0.012, j, sprintf('%d  (%.1f%%)', exc_c_s(j), exc_c_s(j)/tot5*100), 'VerticalAlignment','middle','FontSize',9,'Color',[0.3 0.3 0.3]);
    end
    ax5.XLim(2) = max(exc_c_s)*1.30;

    if SAVE_FIGS, save_fig(fig5, OUT_DIR, 'fig5_exception_frequency'); end
end

%% --- Figure 6: Hit-count rank scatter per project ---
fprintf('Generating Fig 6...\n');
% Only show clean kills, dirty kills, and survivals (exclude Un-hit and Timed Out)
SCATTER_OUTCOME_ORDER  = {'Clean Kill','Dirty Kill','Survived'};
SCATTER_OUTCOME_LABELS = {'Clean Kill','Dirty Kill','Survived'};
scatter_oc_colors = {C_CLEAN, C_DIRTY, C_SURVIVE};

ncols6 = min(nP,3);
nrows6 = ceil(nP/ncols6);
fig6 = figure('Position',[100 100 ncols6*390 nrows6*320], 'Color','w');
last_ax6 = [];

for i = 1:nP
    mask = strcmp(probe_projects, projects{i});
    h_proj = probe_hits(mask);
    out_proj = probe_outcomes(mask);

    % Filter to only executed, non-timeout probes with meaningful outcomes
    keep = strcmp(out_proj,'Clean Kill') | strcmp(out_proj,'Dirty Kill') | strcmp(out_proj,'Survived');
    h_proj = h_proj(keep);
    out_proj = out_proj(keep);

    [h_sorted, sort_idx] = sort(h_proj, 'descend');
    out_sorted = out_proj(sort_idx);
    ranks = 1:numel(h_sorted);

    ax6 = subplot(nrows6, ncols6, i);
    hold(ax6,'on');

    for k = 1:numel(SCATTER_OUTCOME_ORDER)
        sel = strcmp(out_sorted, SCATTER_OUTCOME_ORDER{k});
        if any(sel)
            scatter(ax6, ranks(sel), h_sorted(sel)+0.5, 14, scatter_oc_colors{k}, 'filled', 'MarkerFaceAlpha',0.60, 'DisplayName', SCATTER_OUTCOME_LABELS{k});
        end
    end

    yline(ax6, 1.5, ':', 'Color',[0.55 0.55 0.55], 'LineWidth',1.1, 'HandleVisibility','off');
    ax6.YScale = 'log';
    ax6.Title.String = projects{i};
    ax6.Title.FontWeight = 'bold';
    ax6.Box = 'off';
    ax6.YGrid = 'on';
    ax6.XGrid = 'on';
    ax6.GridAlpha = 0.12;

    n_shown = numel(h_sorted);
    text(ax6, max(n_shown*0.03,1), max(h_sorted)*0.35, sprintf('n=%d shown', n_shown), 'HorizontalAlignment','left','FontSize',7.5,'Color',[0.4 0.4 0.4]);
    hold(ax6,'off');
    last_ax6 = ax6;
end

legend(last_ax6, 'Location','southeast','Box','off','FontSize',9);
sgtitle(fig6, 'Probe Hit-Count Rank per Project (Clean/Dirty/Survived)', 'FontWeight','bold','FontSize',12);

if SAVE_FIGS, save_fig(fig6, OUT_DIR, 'fig6_rank_scatter_per_project'); end

%% --- Figure 6b: Hit-count rank scatter (JSemVer, Joda-Money, Commons-CSV on one line) ---
fprintf('Generating Fig 6b...\n');

target_projects = {'JSemVer', 'Joda-Money', 'Commons-CSV'};
nT = numel(target_projects);

% Create a figure wide enough to hold 3 plots in a single row
fig6b = figure('Position',[100 100 nT*390 280], 'Color','w');
last_ax6b = [];

for i = 1:nT
    proj_name = target_projects{i};
    mask = strcmp(probe_projects, proj_name);
    h_proj = probe_hits(mask);
    out_proj = probe_outcomes(mask);
    
    % Filter to only executed, non-timeout probes with meaningful outcomes
    keep = strcmp(out_proj,'Clean Kill') | strcmp(out_proj,'Dirty Kill') | strcmp(out_proj,'Survived');
    h_proj = h_proj(keep);
    out_proj = out_proj(keep);
    
    [h_sorted, sort_idx] = sort(h_proj, 'descend');
    out_sorted = out_proj(sort_idx);
    ranks = 1:numel(h_sorted);
    
    % Use 1 row, 3 columns to put them all on a single line
    ax6b = subplot(1, nT, i);
    hold(ax6b,'on');
    
    for k = 1:numel(SCATTER_OUTCOME_ORDER)
        sel = strcmp(out_sorted, SCATTER_OUTCOME_ORDER{k});
        if any(sel)
            scatter(ax6b, ranks(sel), h_sorted(sel)+0.5, 14, scatter_oc_colors{k}, 'filled', 'MarkerFaceAlpha',0.60, 'DisplayName', SCATTER_OUTCOME_LABELS{k});
        end
    end
    
    yline(ax6b, 1.5, ':', 'Color',[0.55 0.55 0.55], 'LineWidth',1.1, 'HandleVisibility','off');
    ax6b.YScale = 'log';
    ax6b.Title.String = proj_name;
    ax6b.Title.FontWeight = 'bold';
    ax6b.Box = 'off';
    ax6b.YGrid = 'on';
    ax6b.XGrid = 'on';
    ax6b.GridAlpha = 0.12;
    
    n_shown = numel(h_sorted);
    text(ax6b, max(n_shown*0.03,1), max(h_sorted)*0.35, sprintf('n=%d shown', n_shown), 'HorizontalAlignment','left','FontSize',7.5,'Color',[0.4 0.4 0.4]);
    hold(ax6b,'off');
    last_ax6b = ax6b;
end

% Add legend to the last axis
legend(last_ax6b, 'Location','northeast','Box','off','FontSize',9);
sgtitle(fig6b, 'Probe Hit-Count Rank (Selected Projects)', 'FontWeight','bold','FontSize',12);

if SAVE_FIGS, save_fig(fig6b, OUT_DIR, 'fig6b_rank_scatter_selected'); end

%% --- Figure 7: Hit-count rank scatter aggregated ---
fprintf('Generating Fig 7...\n');
% Filter to clean kills, dirty kills, and survivals only
keep_all = strcmp(probe_outcomes,'Clean Kill') | strcmp(probe_outcomes,'Dirty Kill') | strcmp(probe_outcomes,'Survived');
h_filt = probe_hits(keep_all);
out_filt = probe_outcomes(keep_all);

[h_all_s, all_sort_idx] = sort(h_filt, 'descend');
out_all_s = out_filt(all_sort_idx);
n_all = numel(h_all_s);
ranks_all = 1:n_all;

fig7s = figure('Position',[100 100 FIG_W FIG_H+120], 'Color','w');

% Top scatter plot
ax7_top = subplot(4, 1, [1 2 3]);
hold(ax7_top, 'on');
for k = 1:numel(SCATTER_OUTCOME_ORDER)
    sel = strcmp(out_all_s, SCATTER_OUTCOME_ORDER{k});
    if any(sel)
        scatter(ax7_top, ranks_all(sel), h_all_s(sel)+0.5, 20, scatter_oc_colors{k}, 'filled', 'MarkerFaceAlpha', 0.50, 'DisplayName', SCATTER_OUTCOME_LABELS{k});
    end
end
yline(ax7_top, 1.5, ':', 'Color',[0.55 0.55 0.55], 'LineWidth',1.1, 'HandleVisibility','off');
ax7_top.YScale = 'log';
ax7_top.Title.String = 'Probe Hit-Count Rank & Outcome Probabilities (Clean/Dirty/Survived)';
ax7_top.Title.FontWeight = 'bold';
ax7_top.Box = 'off';
ax7_top.YGrid = 'on'; ax7_top.XGrid = 'on'; ax7_top.GridAlpha = 0.12;
ax7_top.XTickLabel = []; 
legend(ax7_top, 'Location', 'northeast', 'Box', 'off');

text(ax7_top, n_all*0.03, max(h_all_s)*0.40, sprintf('n=%d probes shown', n_all), 'HorizontalAlignment','left','FontSize',9,'Color',[0.4 0.4 0.4]);
hold(ax7_top, 'off');

% Bottom smooth trendlines (Gaussian window applied)
ax7_bot = subplot(4, 1, 4);
hold(ax7_bot, 'on');
is_clean   = double(strcmp(out_all_s, 'Clean Kill'))  * 100;
is_dirty   = double(strcmp(out_all_s, 'Dirty Kill'))  * 100;
is_survive = double(strcmp(out_all_s, 'Survived'))    * 100;

window_size = max(50, round(n_all * 0.40));
smooth_clean   = smoothdata(is_clean,   'gaussian', window_size);
smooth_dirty   = smoothdata(is_dirty,   'gaussian', window_size);
smooth_survive = smoothdata(is_survive, 'gaussian', window_size);

plot(ax7_bot, ranks_all, smooth_clean,   '-', 'LineWidth', 2.5, 'Color', C_CLEAN,   'DisplayName', 'Clean Kill %');
plot(ax7_bot, ranks_all, smooth_dirty,   '-', 'LineWidth', 2.5, 'Color', C_DIRTY,   'DisplayName', 'Dirty Kill %');
plot(ax7_bot, ranks_all, smooth_survive, '-', 'LineWidth', 2.5, 'Color', C_SURVIVE, 'DisplayName', 'Survived %');

ax7_bot.YLim = [0 100];
ax7_bot.Box = 'off';
ax7_bot.YGrid = 'on'; ax7_bot.XGrid = 'on'; ax7_bot.GridAlpha = 0.12;
legend(ax7_bot, 'Location', 'eastoutside', 'Box', 'off');
linkaxes([ax7_top, ax7_bot], 'x');
ax7_top.XLim = [1, max(n_all,1)];
hold(ax7_bot, 'off');

if SAVE_FIGS, save_fig(fig7s, OUT_DIR, 'fig7_rank_scatter_aggregated'); end

%% --- Figure 8: Test execution efficiency ---
fprintf('Generating Fig 8...\n');
suite_sizes = zeros(nP,1);
mean_tests = zeros(nP,1);
median_tests = zeros(nP,1);
pct_saved = zeros(nP,1);

for i = 1:nP
    mask = strcmp(probe_projects, projects{i});
    if isKey(FULL_SUITE_SIZES, projects{i}) && FULL_SUITE_SIZES(projects{i}) > 0
        suite_sizes(i) = FULL_SUITE_SIZES(projects{i});
    else
        suite_sizes(i) = max(probe_unique_hits(mask));
    end

    hits_proj = probe_unique_hits(mask);
    executed = hits_proj(hits_proj > 0);
    if isempty(executed)
        mean_tests(i) = 0;
        median_tests(i) = 0;
    else
        mean_tests(i) = mean(executed);
        median_tests(i) = median(executed);
    end
    pct_saved(i) = (1 - mean_tests(i) / max(suite_sizes(i),1)) * 100;
end

suite_all = [suite_sizes; mean(suite_sizes)];
mean_all = [mean_tests; mean(mean_tests)];
median_all = [median_tests; mean(median_tests)];
labs7 = [projects, {'Avg (all)'}];
nBars7 = nP + 1;

fig8a = figure('Position',[100 100 FIG_W FIG_H], 'Color','w');
ax8a = axes(fig8a);
b8a = bar(ax8a, [suite_all, mean_all, median_all], 'grouped', 'BarWidth',0.72);
b8a(1).FaceColor = [0.40 0.62 0.82]; b8a(1).EdgeColor = 'none'; 
b8a(2).FaceColor = [0.85 0.55 0.35]; b8a(2).EdgeColor = 'none'; 
b8a(3).FaceColor = [0.95 0.80 0.25]; b8a(3).EdgeColor = 'none'; 

xline(ax8a, nP+0.5, '--', 'Color',[0.6 0.6 0.6], 'LineWidth',1.2, 'Alpha',0.6);
ax8a.XTick = 1:nBars7;
ax8a.XTickLabel = labs7;
ax8a.XTickLabelRotation = 20;
ax8a.Title.String = 'Test Execution Efficiency';
ax8a.Title.FontWeight = 'bold';
ax8a.Box = 'off';
ax8a.YGrid = 'on'; ax8a.GridAlpha = 0.15;
legend(ax8a, {'Full suite', 'Mean tests/probe', 'Median tests/probe'}, 'Location','northeastoutside','Box','off');

bw7 = 0.72 / 4;
yc7 = ax8a.YLim(2);
for i = 1:nBars7
    if suite_all(i) > 0
        saved_pct = (1 - mean_all(i)/max(suite_all(i),1)) * 100;
        text(ax8a, i - bw7, suite_all(i) + yc7*0.018, sprintf('%.0f%% skipped', saved_pct), 'HorizontalAlignment','center','FontSize',8, 'Color',[0.18 0.34 0.54],'FontWeight','bold');
    end
    text(ax8a, i, mean_all(i) + yc7*0.018, sprintf('%.0f', mean_all(i)), 'HorizontalAlignment','center','FontSize',8,'Color',[0.50 0.28 0.10]);
    text(ax8a, i + bw7, median_all(i) + yc7*0.018, sprintf('%.0f', median_all(i)), 'HorizontalAlignment','center','FontSize',8,'Color',[0.55 0.48 0.05]);
end

if SAVE_FIGS, save_fig(fig8a, OUT_DIR, 'fig8_test_efficiency'); end

%% --- Figure 9: Exception type breakdown per project ---
fprintf('Generating Fig 9...\n');
dirty_te = strcmp(exec_outcomes,'FAIL by Exception');
all_excs = exec_excs(dirty_te);
all_excs = all_excs(~strcmp(all_excs,'none') & ~strcmp(all_excs,'Unknown'));

if ~isempty(all_excs)
    [exc_u, ~, ic_u] = unique(all_excs);
    exc_glob_cnt = accumarray(ic_u(:), 1);
    [~, exc_sort] = sort(exc_glob_cnt,'descend');
    top_exc = exc_u(exc_sort(1:min(5, numel(exc_u))));
    nExc = numel(top_exc);

    exc_matrix = zeros(nP, nExc+1);
    exec_proj_te2 = {test_execs.project};
    for i = 1:nP
        proj_dirty = dirty_te & strcmp(exec_proj_te2, projects{i});
        proj_excs = exec_excs(proj_dirty);
        proj_excs = proj_excs(~strcmp(proj_excs,'none') & ~strcmp(proj_excs,'Unknown'));
        tot_proj = numel(proj_excs);
        if tot_proj == 0, continue; end
        for e = 1:nExc
            exc_matrix(i,e) = sum(strcmp(proj_excs, top_exc{e}));
        end
        exc_matrix(i,end) = tot_proj - sum(exc_matrix(i,1:nExc));
    end

    exc_totals = sum(exc_matrix,2);
    exc_pct = exc_matrix ./ max(exc_totals,1) * 100;
    exc_cmap = [0.95 0.80 0.25; 0.85 0.35 0.35; 0.40 0.62 0.82; 0.55 0.78 0.50; 0.80 0.50 0.75; 0.72 0.72 0.72];
    exc_labels_all = [top_exc(:); {'Other'}];

    fig9 = figure('Position',[100 100 FIG_W FIG_H], 'Color','w');
    ax9 = axes(fig9);
    b9 = bar(ax9, exc_pct, 'stacked', 'BarWidth',0.6);
    for e = 1:nExc+1
        b9(e).FaceColor = exc_cmap(e,:);
        b9(e).EdgeColor = 'none';
    end

    ax9.XTick = 1:nP;
    ax9.XTickLabel = projects;
    ax9.XTickLabelRotation = 20;
    ax9.YLim = [0 118];
    ax9.Title.String = 'Exception Type Profile per Project (Top 5)';
    ax9.Title.FontWeight = 'bold';
    ax9.Box = 'off';
    ax9.YGrid = 'on'; ax9.GridAlpha = 0.15;
    legend(ax9, exc_labels_all, 'Location','northeastoutside','Box','off');

    for i = 1:nP
        text(ax9, i, 102, sprintf('n=%d', exc_totals(i)), 'HorizontalAlignment','center','FontSize',8.5, 'Color',[0.25 0.25 0.25],'FontWeight','bold');
        cum_exc = 0;
        for e = 1:nExc+1
            if exc_pct(i,e) >= 7
                text(ax9, i, cum_exc + exc_pct(i,e)/2, sprintf('%.0f%%',exc_pct(i,e)), 'HorizontalAlignment','center','FontSize',8, 'Color','w','FontWeight','bold');
            end
            cum_exc = cum_exc + exc_pct(i,e);
        end
    end

    if SAVE_FIGS, save_fig(fig9, OUT_DIR, 'fig9_exception_breakdown'); end
end

%% --- Figure 10: Probe outcome by unique-tests-hit threshold ---
fprintf('Generating Fig 10...\n');
bins_9 = {1, [2 5], [6 15], 16};
bin_labels_9 = {'Exactly 1 test','2–5 tests','6–15 tests','16+ tests'};
nBins_9 = numel(bins_9);
exec_mask_9 = ~strcmp(probe_outcomes,'Un-hit') & ~strcmp(probe_outcomes,'Timed Out');

pct_9 = zeros(nBins_9, numel(OUTCOME_ORDER));
tot_9 = zeros(nBins_9, 1);
for b = 1:nBins_9
    bd = bins_9{b};
    if numel(bd)==1 && b<nBins_9, in_bin = probe_unique_hits == bd(1);
    elseif numel(bd)==2, in_bin = probe_unique_hits >= bd(1) & probe_unique_hits <= bd(2);
    else, in_bin = probe_unique_hits >= bd(1);
    end
    in_bin = in_bin & exec_mask_9;
    tot_9(b) = sum(in_bin);
    for k = 1:numel(OUTCOME_ORDER)
        pct_9(b,k) = sum(in_bin & strcmp(probe_outcomes,OUTCOME_ORDER{k})) / max(tot_9(b),1) * 100;
    end
end

ck_proj_9 = NaN(nP, nBins_9);
for i = 1:nP
    pm = strcmp(probe_projects, projects{i}) & exec_mask_9;
    for b = 1:nBins_9
        bd = bins_9{b};
        if numel(bd)==1 && b<nBins_9, in_bin = probe_unique_hits == bd(1);
        elseif numel(bd)==2, in_bin = probe_unique_hits >= bd(1) & probe_unique_hits <= bd(2);
        else, in_bin = probe_unique_hits >= bd(1);
        end
        in_bin = in_bin & pm;
        if sum(in_bin) < 3, continue; end
        ck_proj_9(i,b) = sum(in_bin & strcmp(probe_outcomes,'Clean Kill')) / sum(in_bin) * 100;
    end
end

fig10 = figure('Position',[100 100 FIG_W 350], 'Color','w');

ax10L = subplot(1,2,1);
draw_stacked(ax10L, pct_9(:,1:3), tot_9, bin_labels_9, OUTCOME_COLORS(1:3,:), OUTCOME_LABELS(1:3), 5);
ax10L.Title.String = 'Outcome by Coverage Depth';
ax10L.Title.FontWeight = 'bold';
ax10L.XTickLabelRotation = 12;

ax10R = subplot(1,2,2);
b10R = bar(ax10R, ck_proj_9', 'grouped', 'BarWidth',0.8);
for i = 1:nP
    b10R(i).FaceColor = proj_cmap(i,:);
    b10R(i).EdgeColor = 'none';
    b10R(i).FaceAlpha = 0.88;
end

agg_ck_9 = pct_9(:,1);
hold(ax10R,'on');
plot(ax10R, 1:nBins_9, agg_ck_9, 'k--o', 'LineWidth',2.5, 'MarkerSize',7, 'MarkerFaceColor','k', 'DisplayName','All Projects avg');
hold(ax10R,'off');

ax10R.XTick = 1:nBins_9;
ax10R.XTickLabel = bin_labels_9;
ax10R.XTickLabelRotation = 12;
ax10R.YLim = [0 100];
ax10R.Title.String = 'Clean Kill Rate per Project';
ax10R.Title.FontWeight = 'bold';
ax10R.Box = 'off';
ax10R.YGrid = 'on'; ax10R.XGrid = 'on'; ax10R.GridAlpha = 0.14;
legend(ax10R, [projects, {'All Projects avg'}], 'Location','northwest','Box','off');

sgtitle(fig10, 'Probe Outcome by Number of Tests Hitting It', 'FontWeight','bold','FontSize',13);
if SAVE_FIGS, save_fig(fig10, OUT_DIR, 'fig10_outcome_by_coverage_depth'); end

fprintf('\nDone. All 10 figures generated.\n');

%% --- Helper Functions ---
function save_fig(fig, out_dir, name)
    png_name = fullfile(out_dir, [name '.png']);
    exportgraphics(fig, png_name, 'Resolution', 300);
    pdf_name = fullfile(out_dir, [name '.pdf']);
    exportgraphics(fig, pdf_name, 'ContentType', 'vector', 'BackgroundColor', 'none');
end

function [pct, abs_c, totals] = outcome_matrix(group_var, outcomes, group_list, order)
    nG = numel(group_list);
    nK = numel(order);
    abs_c = zeros(nG, nK);
    for i = 1:nG
        mask = strcmp(group_var, group_list{i});
        for k = 1:nK
            abs_c(i,k) = sum(strcmp(outcomes(mask), order{k}));
        end
    end
    totals = sum(abs_c, 2);
    pct = abs_c ./ max(totals,1) * 100;
end

function draw_stacked(ax, pct, totals, x_labels, colors, leg_labels, min_pct)
    nG = size(pct,1);
    nK = size(colors,1);
    b = bar(ax, pct, 'stacked', 'BarWidth', 0.6);
    for k = 1:nK
        b(k).FaceColor = colors(k,:);
        b(k).EdgeColor = 'none';
    end
    ax.XTick = 1:nG;
    ax.XTickLabel = x_labels;
    ax.XTickLabelRotation = 20;
    ax.YLim = [0 118];
    ax.Box = 'off';
    ax.YGrid = 'on';
    ax.GridAlpha = 0.15;
    legend(ax, leg_labels, 'Location','northeastoutside','Box','off');
    for i = 1:nG
        text(ax, i, 101 + 118*0.022, sprintf('n=%d', totals(i)), 'HorizontalAlignment','center','FontSize',8.5, 'Color',[0.25 0.25 0.25],'FontWeight','bold');
    end
    for k = 1:nK
        for i = 1:nG
            if pct(i,k) >= min_pct
                base = sum(pct(i,1:k-1));
                text(ax, i, base + pct(i,k)/2, sprintf('%.0f%%', pct(i,k)), 'HorizontalAlignment','center','FontSize',8, 'Color','w','FontWeight','bold');
            end
        end
    end
end