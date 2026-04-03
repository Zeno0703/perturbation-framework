clear; clc; close all;

%% --- Configuration ---
DB_PATH = '../data/database.json';
FULL_SUITE_SIZES = containers.Map( ...
    {'JSemVer', 'Joda-Money', 'Textr', 'Commons-CLI', 'Commons-CSV', 'Commons-Validator'}, ...
    {334, 1495, 249, 977, 923, 992} ...
);
SAVE_FIGS = true;
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

%% --- Figure 2: Probe outcome by operator type aggregated ---
fprintf('Generating Fig 2...\n');
exec_mask = ~strcmp(probe_outcomes,'Un-hit') & ~strcmp(probe_outcomes,'Timed Out');
all_ops = sort(unique(probe_operators(exec_mask)));
nOps = numel(all_ops);

[pct2, ~, tot2] = outcome_matrix(probe_operators(exec_mask), probe_outcomes(exec_mask), all_ops, OUTCOME_ORDER);
[~, si2] = sort(pct2(:,1),'descend');
pct2 = pct2(si2,:);  
tot2 = tot2(si2);  
ops2 = all_ops(si2);

fig2 = figure('Position',[100 100 max(FIG_W, nOps*130+220) FIG_H], 'Color','w');
ax2  = axes(fig2);
draw_stacked(ax2, pct2(:,1:3), tot2, ops2, OUTCOME_COLORS(1:3,:), OUTCOME_LABELS(1:3), 5);
ax2.Title.String = 'Probe Outcome by Operator Type — Aggregated';
ax2.Title.FontWeight = 'bold';

if SAVE_FIGS, save_fig(fig2, OUT_DIR, 'fig2_outcome_by_operator'); end

%% --- Figure 3: Unique probes vs total hits, per project + avg ---
fprintf('Generating Fig 3...\n');
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

fig3 = figure('Position',[100 100 FIG_W FIG_H], 'Color','w');
ax3  = axes(fig3);

b3 = bar(ax3, [n_unique_all, n_hits_all], 'grouped', 'BarWidth',0.6);
b3(1).FaceColor = [0.40 0.62 0.82]; b3(1).EdgeColor = 'none';
b3(2).FaceColor = [0.85 0.55 0.35]; b3(2).EdgeColor = 'none';

xline(ax3, nP+0.5, '--', 'Color',[0.6 0.6 0.6], 'LineWidth',1.2, 'Alpha',0.6);
ax3.XTick = 1:nBars3;
ax3.XTickLabel = labs3;
ax3.XTickLabelRotation = 20;
ax3.YLabel.String = 'Count';
ax3.Title.String = 'Unique Probes vs Total Test Hits';
ax3.Title.FontWeight = 'bold';
ax3.Box = 'off';
ax3.YGrid = 'on';
ax3.GridAlpha = 0.15;
legend(ax3, {'Unique probes','Total hits'}, 'Location','northeastoutside','Box','off');

bw3 = 0.6/3;
yc3 = ax3.YLim(2);
for i = 1:nBars3
    ratio = n_hits_all(i) / max(n_unique_all(i),1);
    text(ax3, i+bw3, n_hits_all(i)+yc3*0.018, sprintf('×%.1f',ratio), 'HorizontalAlignment','center','FontSize',9.5, 'Color',[0.55 0.22 0.05],'FontWeight','bold');
    text(ax3, i-bw3, n_unique_all(i)+yc3*0.018, sprintf('%d',round(n_unique_all(i))), 'HorizontalAlignment','center','FontSize',8,'Color',[0.18 0.34 0.54]);
end

if SAVE_FIGS, save_fig(fig3, OUT_DIR, 'fig3_hits_vs_probes'); end

%% --- Figure 4: Exception type frequency ---
fprintf('Generating Fig 4...\n');
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

    fig4 = figure('Position',[100 100 FIG_W max(FIG_H, top_n*42+120)], 'Color','w');
    ax4  = axes(fig4);
    barh(ax4, exc_c_s, 'FaceColor',C_DIRTY, 'EdgeColor','none', 'BarWidth',0.65);
    ax4.YTick = 1:top_n;
    ax4.YTickLabel = exc_n_s;
    ax4.XLabel.String = 'Frequency';
    ax4.Title.String = 'Exception Types in Dirty-Kill Executions';
    ax4.Title.FontWeight = 'bold';
    ax4.Box = 'off';
    ax4.XGrid = 'on';
    ax4.GridAlpha = 0.15;
    ax4.YDir = 'reverse';

    tot4 = sum(exc_c_s);
    for j = 1:top_n
        text(ax4, exc_c_s(j)+max(exc_c_s)*0.012, j, sprintf('%d  (%.1f%%)', exc_c_s(j), exc_c_s(j)/tot4*100), 'VerticalAlignment','middle','FontSize',9,'Color',[0.3 0.3 0.3]);
    end
    ax4.XLim(2) = max(exc_c_s)*1.30;

    if SAVE_FIGS, save_fig(fig4, OUT_DIR, 'fig4_exception_frequency'); end
end

%% --- Figure 5: Hit-count rank scatter per project ---
fprintf('Generating Fig 5...\n');
oc_colors = {C_CLEAN, C_DIRTY, C_SURVIVE, C_UNHIT, C_TIMEOUT};

ncols5 = min(nP,3);
nrows5 = ceil(nP/ncols5);
fig5 = figure('Position',[100 100 ncols5*390 nrows5*320], 'Color','w');
last_ax5 = [];

for i = 1:nP
    mask = strcmp(probe_projects, projects{i});
    h_proj = probe_hits(mask);
    out_proj = probe_outcomes(mask);

    [h_sorted, sort_idx] = sort(h_proj, 'descend');
    out_sorted = out_proj(sort_idx);
    ranks = 1:numel(h_sorted);

    ax5 = subplot(nrows5, ncols5, i);
    hold(ax5,'on');

    for k = 1:numel(OUTCOME_ORDER)
        sel = strcmp(out_sorted, OUTCOME_ORDER{k});
        if any(sel)
            scatter(ax5, ranks(sel), h_sorted(sel)+0.5, 14, oc_colors{k}, 'filled', 'MarkerFaceAlpha',0.60, 'DisplayName', OUTCOME_LABELS{k});
        end
    end

    yline(ax5, 1.5, ':', 'Color',[0.55 0.55 0.55], 'LineWidth',1.1, 'HandleVisibility','off');
    ax5.YScale = 'log';
    ax5.Title.String = projects{i};
    ax5.Title.FontWeight = 'bold';
    ax5.Box = 'off';
    ax5.YGrid = 'on';
    ax5.XGrid = 'on';
    ax5.GridAlpha = 0.12;

    n_total = numel(h_sorted);
    n_exec = sum(h_sorted > 0);
    text(ax5, n_total*0.03, ax5.YLim(1)*1.8, sprintf('n=%d  |  %d executed', n_total, n_exec), 'HorizontalAlignment','left','FontSize',7.5,'Color',[0.4 0.4 0.4]);
    hold(ax5,'off');
    last_ax5 = ax5;
end

legend(last_ax5, 'Location','southeast','Box','off','FontSize',9);
sgtitle(fig5, 'Probe Hit-Count Rank per Project', 'FontWeight','bold','FontSize',12);

if SAVE_FIGS, save_fig(fig5, OUT_DIR, 'fig5_rank_scatter_per_project'); end

%% --- Figure 6: Hit-count rank scatter aggregated ---
fprintf('Generating Fig 6...\n');
[h_all_s, all_sort_idx] = sort(probe_hits, 'descend');
out_all_s = probe_outcomes(all_sort_idx);
n_all = numel(h_all_s);
ranks_all = 1:n_all;

fig6 = figure('Position',[100 100 FIG_W FIG_H+120], 'Color','w');

% Top scatter plot
ax6_top = subplot(4, 1, [1 2 3]);
hold(ax6_top, 'on');
for k = 1:numel(OUTCOME_ORDER)
    sel = strcmp(out_all_s, OUTCOME_ORDER{k});
    if any(sel)
        scatter(ax6_top, ranks_all(sel), h_all_s(sel)+0.5, 20, oc_colors{k}, 'filled', 'MarkerFaceAlpha', 0.50, 'DisplayName', OUTCOME_LABELS{k});
    end
end
yline(ax6_top, 1.5, ':', 'Color',[0.55 0.55 0.55], 'LineWidth',1.1, 'HandleVisibility','off');
ax6_top.YScale = 'log';
ax6_top.Title.String = 'Probe Hit-Count Rank & Outcome Probabilities';
ax6_top.Title.FontWeight = 'bold';
ax6_top.Box = 'off';
ax6_top.YGrid = 'on'; ax6_top.XGrid = 'on'; ax6_top.GridAlpha = 0.12;
ax6_top.XTickLabel = []; 
legend(ax6_top, 'Location', 'northeast', 'Box', 'off');

n_exec_all = sum(h_all_s > 0);
text(ax6_top, n_all*0.03, ax6_top.YLim(2)*0.40, sprintf('n=%d probes\n%d executed', n_all, n_exec_all), 'HorizontalAlignment','left','FontSize',9,'Color',[0.4 0.4 0.4]);
hold(ax6_top, 'off');

% Bottom smooth trendlines (Gaussian window applied)
ax6_bot = subplot(4, 1, 4);
hold(ax6_bot, 'on');
is_clean = double(strcmp(out_all_s, 'Clean Kill')) * 100;
is_dirty = double(strcmp(out_all_s, 'Dirty Kill')) * 100;
is_survive = double(strcmp(out_all_s, 'Survived')) * 100;

window_size = max(50, round(n_all * 0.40));
smooth_clean = smoothdata(is_clean, 'gaussian', window_size);
smooth_dirty = smoothdata(is_dirty, 'gaussian', window_size);
smooth_survive = smoothdata(is_survive, 'gaussian', window_size);

plot(ax6_bot, ranks_all, smooth_clean, '-', 'LineWidth', 2.5, 'Color', oc_colors{1}, 'DisplayName', 'Clean Kill %');
plot(ax6_bot, ranks_all, smooth_dirty, '-', 'LineWidth', 2.5, 'Color', oc_colors{2}, 'DisplayName', 'Dirty Kill %');
plot(ax6_bot, ranks_all, smooth_survive, '-', 'LineWidth', 2.5, 'Color', oc_colors{3}, 'DisplayName', 'Survived %');

ax6_bot.YLim = [0 100];
ax6_bot.Box = 'off';
ax6_bot.YGrid = 'on'; ax6_bot.XGrid = 'on'; ax6_bot.GridAlpha = 0.12;
legend(ax6_bot, 'Location', 'eastoutside', 'Box', 'off');
linkaxes([ax6_top, ax6_bot], 'x');
ax6_top.XLim = [1, n_all];
hold(ax6_bot, 'off');

if SAVE_FIGS, save_fig(fig6, OUT_DIR, 'fig6_rank_scatter_aggregated'); end

%% --- Figure 7: Test execution efficiency ---
fprintf('Generating Fig 7...\n');
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

fig7 = figure('Position',[100 100 FIG_W FIG_H], 'Color','w');
ax7 = axes(fig7);
b7 = bar(ax7, [suite_all, mean_all, median_all], 'grouped', 'BarWidth',0.72);
b7(1).FaceColor = [0.40 0.62 0.82]; b7(1).EdgeColor = 'none'; 
b7(2).FaceColor = [0.85 0.55 0.35]; b7(2).EdgeColor = 'none'; 
b7(3).FaceColor = [0.95 0.80 0.25]; b7(3).EdgeColor = 'none'; 

xline(ax7, nP+0.5, '--', 'Color',[0.6 0.6 0.6], 'LineWidth',1.2, 'Alpha',0.6);
ax7.XTick = 1:nBars7;
ax7.XTickLabel = labs7;
ax7.XTickLabelRotation = 20;
ax7.Title.String = 'Test Execution Efficiency';
ax7.Title.FontWeight = 'bold';
ax7.Box = 'off';
ax7.YGrid = 'on'; ax7.GridAlpha = 0.15;
legend(ax7, {'Full suite', 'Mean tests/probe', 'Median tests/probe'}, 'Location','northeastoutside','Box','off');

bw7 = 0.72 / 4;
yc7 = ax7.YLim(2);
for i = 1:nBars7
    if suite_all(i) > 0
        saved_pct = (1 - mean_all(i)/max(suite_all(i),1)) * 100;
        text(ax7, i - bw7, suite_all(i) + yc7*0.018, sprintf('%.0f%% skipped', saved_pct), 'HorizontalAlignment','center','FontSize',8, 'Color',[0.18 0.34 0.54],'FontWeight','bold');
    end
    text(ax7, i, mean_all(i) + yc7*0.018, sprintf('%.0f', mean_all(i)), 'HorizontalAlignment','center','FontSize',8,'Color',[0.50 0.28 0.10]);
    text(ax7, i + bw7, median_all(i) + yc7*0.018, sprintf('%.0f', median_all(i)), 'HorizontalAlignment','center','FontSize',8,'Color',[0.55 0.48 0.05]);
end

if SAVE_FIGS, save_fig(fig7, OUT_DIR, 'fig7_test_efficiency'); end

%% --- Figure 8: Exception type breakdown per project ---
fprintf('Generating Fig 8...\n');
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

    fig8 = figure('Position',[100 100 FIG_W FIG_H], 'Color','w');
    ax8 = axes(fig8);
    b8 = bar(ax8, exc_pct, 'stacked', 'BarWidth',0.6);
    for e = 1:nExc+1
        b8(e).FaceColor = exc_cmap(e,:);
        b8(e).EdgeColor = 'none';
    end

    ax8.XTick = 1:nP;
    ax8.XTickLabel = projects;
    ax8.XTickLabelRotation = 20;
    ax8.YLim = [0 118];
    ax8.Title.String = 'Exception Type Profile per Project (Top 5)';
    ax8.Title.FontWeight = 'bold';
    ax8.Box = 'off';
    ax8.YGrid = 'on'; ax8.GridAlpha = 0.15;
    legend(ax8, exc_labels_all, 'Location','northeastoutside','Box','off');

    for i = 1:nP
        text(ax8, i, 102, sprintf('n=%d', exc_totals(i)), 'HorizontalAlignment','center','FontSize',8.5, 'Color',[0.25 0.25 0.25],'FontWeight','bold');
        cum_exc = 0;
        for e = 1:nExc+1
            if exc_pct(i,e) >= 7
                text(ax8, i, cum_exc + exc_pct(i,e)/2, sprintf('%.0f%%',exc_pct(i,e)), 'HorizontalAlignment','center','FontSize',8, 'Color','w','FontWeight','bold');
            end
            cum_exc = cum_exc + exc_pct(i,e);
        end
    end

    if SAVE_FIGS, save_fig(fig8, OUT_DIR, 'fig8_exception_breakdown'); end
end

%% --- Figure 9: Probe outcome by unique-tests-hit threshold ---
fprintf('Generating Fig 9...\n');
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

fig9 = figure('Position',[100 100 FIG_W FIG_H], 'Color','w');

ax9L = subplot(1,2,1);
draw_stacked(ax9L, pct_9(:,1:3), tot_9, bin_labels_9, OUTCOME_COLORS(1:3,:), OUTCOME_LABELS(1:3), 5);
ax9L.Title.String = 'Outcome by Coverage Depth';
ax9L.Title.FontWeight = 'bold';
ax9L.XTickLabelRotation = 12;

ax9R = subplot(1,2,2);
b9R = bar(ax9R, ck_proj_9', 'grouped', 'BarWidth',0.8);
for i = 1:nP
    b9R(i).FaceColor = proj_cmap(i,:);
    b9R(i).EdgeColor = 'none';
    b9R(i).FaceAlpha = 0.88;
end

agg_ck_9 = pct_9(:,1);
hold(ax9R,'on');
plot(ax9R, 1:nBins_9, agg_ck_9, 'k--o', 'LineWidth',2.5, 'MarkerSize',7, 'MarkerFaceColor','k', 'DisplayName','All Projects avg');
hold(ax9R,'off');

ax9R.XTick = 1:nBins_9;
ax9R.XTickLabel = bin_labels_9;
ax9R.XTickLabelRotation = 12;
ax9R.YLim = [0 100];
ax9R.Title.String = 'Clean Kill Rate per Project';
ax9R.Title.FontWeight = 'bold';
ax9R.Box = 'off';
ax9R.YGrid = 'on'; ax9R.XGrid = 'on'; ax9R.GridAlpha = 0.14;
legend(ax9R, [projects, {'All Projects avg'}], 'Location','northwest','Box','off');

sgtitle(fig9, 'Probe Outcome by Number of Tests Hitting It', 'FontWeight','bold','FontSize',13);
if SAVE_FIGS, save_fig(fig9, OUT_DIR, 'fig9_outcome_by_coverage_depth'); end

fprintf('\nDone. Selected figures generated.\n');

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