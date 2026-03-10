function analyse_perturbations()
    % 1. Load and Parse JSON
    fileName = 'database.json';
    if ~isfile(fileName)
        error('File %s not found. Please ensure it is in the same directory.', fileName);
    end
    
    fid = fopen(fileName, 'r');
    rawText = fread(fid, inf, '*char')';
    fclose(fid);
    
    data = jsondecode(rawText);
    probes = data.probes;
    executions = data.test_executions;

    colorClean = [0.18, 0.80, 0.44];   % Emerald Green (Clean Kill / Fail with Assert)
    colorDirty = [0.95, 0.61, 0.07];   % Sunflower Orange (Dirty Kill / Fail with Exception)
    colorSurvive = [0.91, 0.30, 0.24]; % Alizarin Red (Survived / Pass)
    colorNeutral = [0.30, 0.45, 0.65]; % Academic Blue for general stats
    
    function applyAcademicStyle(ax)
        box(ax, 'off');
        ax.TickDir = 'out';
        ax.YGrid = 'on';
        ax.XGrid = 'off';
        ax.GridColor = [0.8 0.8 0.8];
        ax.GridAlpha = 0.5;
        ax.GridLineStyle = '-';
        ax.LineWidth = 1.0;
        ax.FontSize = 11;
        ax.FontName = 'Helvetica'; % Standard academic font, normal weight
    end

    % =====================================================================
    % GENERAL 1: Overall Probe Outcomes
    % =====================================================================
    figG1 = figure('Name', 'Overall Probe Outcomes', 'Color', 'w', 'Position', [50, 50, 700, 500]);
    axG1 = axes(figG1);
    
    outcomesList = {'Clean Kill', 'Dirty Kill', 'Survived'};
    outcomeCounts = [sum(strcmp({probes.probe_outcome}, outcomesList{1})), ...
                     sum(strcmp({probes.probe_outcome}, outcomesList{2})), ...
                     sum(strcmp({probes.probe_outcome}, outcomesList{3}))];
                 
    bG1 = bar(axG1, 1:3, outcomeCounts, 'FaceColor', 'flat', 'EdgeColor', 'none', 'BarWidth', 0.6);
    bG1.CData(1,:) = colorClean; bG1.CData(2,:) = colorDirty; bG1.CData(3,:) = colorSurvive;
    
    for i = 1:3
        text(axG1, i, outcomeCounts(i), sprintf('N=%d\n(%.1f%%)', outcomeCounts(i), (outcomeCounts(i)/sum(outcomeCounts))*100), ...
            'HorizontalAlignment', 'center', 'VerticalAlignment', 'bottom', 'FontSize', 11, 'FontWeight', 'normal');
    end
    
    set(axG1, 'XTick', 1:3, 'XTickLabel', outcomesList);
    ylabel(axG1, 'Total Number of Probes', 'FontSize', 12, 'FontWeight', 'normal');
    title(axG1, 'Overall Probe Outcomes', 'FontSize', 14, 'FontWeight', 'normal');
    ylim(axG1, [0, max(outcomeCounts) * 1.2]); 
    applyAcademicStyle(axG1);

    % =====================================================================
    % GENERAL 2: Test Execution Outcomes Breakdown
    % =====================================================================
    figG2 = figure('Name', 'Test Execution Outcomes', 'Color', 'w', 'Position', [100, 80, 700, 500]);
    axG2 = axes(figG2);
    
    execOutcomes = {'PASS', 'FAIL by Assert', 'FAIL by Exception'};
    execCounts = [sum(strcmp({executions.test_outcome}, execOutcomes{1})), ...
                  sum(strcmp({executions.test_outcome}, execOutcomes{2})), ...
                  sum(strcmp({executions.test_outcome}, execOutcomes{3}))];
              
    bG2 = bar(axG2, 1:3, execCounts, 'FaceColor', 'flat', 'EdgeColor', 'none', 'BarWidth', 0.6);
    bG2.CData(1,:) = colorSurvive; bG2.CData(2,:) = colorClean; bG2.CData(3,:) = colorDirty;
    
    for i = 1:3
        text(axG2, i, execCounts(i), sprintf('N=%d\n(%.1f%%)', execCounts(i), (execCounts(i)/sum(execCounts))*100), ...
            'HorizontalAlignment', 'center', 'VerticalAlignment', 'bottom', 'FontSize', 11, 'FontWeight', 'normal');
    end
    
    set(axG2, 'XTick', 1:3, 'XTickLabel', execOutcomes);
    ylabel(axG2, 'Total Number of Test Executions', 'FontSize', 12, 'FontWeight', 'normal');
    title(axG2, 'Test Execution Results', 'FontSize', 14, 'FontWeight', 'normal');
    ylim(axG2, [0, max(execCounts) * 1.2]);
    applyAcademicStyle(axG2);

    % =====================================================================
    % GENERAL 3: Exception Profile (Dirty Kills)
    % =====================================================================
    figG3 = figure('Name', 'Exception Profile', 'Color', 'w', 'Position', [150, 110, 850, 500]);
    axG3 = axes(figG3);
    
    exceptions = {executions.exception};
    validExIdx = ~strcmp(exceptions, 'none');
    validExceptions = exceptions(validExIdx);
    
    if ~isempty(validExceptions)
        [uniqueEx, ~, idx] = unique(validExceptions);
        exCounts = accumarray(idx, 1);
        [sortedCounts, sortIdx] = sort(exCounts, 'descend');
        
        numToShow = min(8, length(sortedCounts)); 
        topCounts = sortedCounts(1:numToShow);
        topEx = uniqueEx(sortIdx(1:numToShow));
        
        bG3 = barh(axG3, 1:numToShow, flip(topCounts), 'FaceColor', colorDirty, 'EdgeColor', 'none');
        
        for i = 1:numToShow
            text(axG3, flip(topCounts(i)) + (max(topCounts)*0.02), numToShow - i + 1, sprintf('N=%d', flip(topCounts(i))), ...
                'VerticalAlignment', 'middle', 'FontSize', 10, 'FontWeight', 'normal');
        end
        
        set(axG3, 'YTick', 1:numToShow, 'YTickLabel', flip(topEx), 'TickLabelInterpreter', 'none');
        xlabel(axG3, 'Frequency of Exception', 'FontSize', 12, 'FontWeight', 'normal');
        title(axG3, 'Top Exceptions Causing Dirty Kills', 'FontSize', 14, 'FontWeight', 'normal');
        axG3.YGrid = 'off'; axG3.XGrid = 'on';
        applyAcademicStyle(axG3);
        xlim(axG3, [0, max(topCounts) * 1.15]);
    else
        title(axG3, 'No Exceptions Recorded', 'FontSize', 14, 'FontWeight', 'normal');
    end

    % =====================================================================
    % ANALYSIS 1: Operator Efficacy (100% Stacked Bar)
    % =====================================================================
    figA1 = figure('Name', 'Operator Efficacy', 'Color', 'w', 'Position', [200, 140, 850, 550]);
    axA1 = axes(figA1);
    
    operators = unique({probes.operator});
    numOps = length(operators);
    outcomesMatrix = zeros(numOps, 3); 
    totals = zeros(numOps, 1);
    
    for i = 1:numOps
        opProbes = probes(strcmp({probes.operator}, operators{i}));
        totals(i) = length(opProbes);
        outcomesMatrix(i, 1) = sum(strcmp({opProbes.probe_outcome}, 'Clean Kill'));
        outcomesMatrix(i, 2) = sum(strcmp({opProbes.probe_outcome}, 'Dirty Kill'));
        outcomesMatrix(i, 3) = sum(strcmp({opProbes.probe_outcome}, 'Survived'));
    end
    
    percentMatrix = (outcomesMatrix ./ totals) * 100;
    percentMatrix(isnan(percentMatrix)) = 0; 
    
    bA1 = bar(axA1, 1:numOps, percentMatrix, 'stacked', 'EdgeColor', 'none');
    bA1(1).FaceColor = colorClean; bA1(2).FaceColor = colorDirty; bA1(3).FaceColor = colorSurvive;
    
    for i = 1:numOps
        text(axA1, i, 103, sprintf('N=%d', totals(i)), 'HorizontalAlignment', 'center', ...
            'FontSize', 10, 'Color', [0.2 0.2 0.2], 'FontWeight', 'normal');
    end
    
    set(axA1, 'XTick', 1:numOps, 'XTickLabel', operators); xtickangle(axA1, 30);
    legend(axA1, 'Clean Kill', 'Dirty Kill', 'Survived', 'Location', 'southoutside', 'Orientation', 'horizontal', 'Box', 'off');
    ylabel(axA1, 'Proportion of Outcomes (%)', 'FontSize', 12, 'FontWeight', 'normal');
    xlabel(axA1, 'Perturbation Operator', 'FontSize', 12, 'FontWeight', 'normal');
    title(axA1, 'Operator Efficacy', 'FontSize', 14, 'FontWeight', 'normal');
    ylim(axA1, [0 115]); 
    applyAcademicStyle(axA1);

    % =====================================================================
    % ANALYSIS 2: Vulnerability Location Rates
    % =====================================================================
    figA2 = figure('Name', 'Vulnerability Location', 'Color', 'w', 'Position', [250, 170, 850, 550]);
    axA2 = axes(figA2);
    
    locations = {'Argument', 'Return', 'Variable'}; 
    rateMatrix = zeros(length(locations), 3); 
    locTotals = zeros(length(locations), 1);
    
    for i = 1:length(locations)
        idx = strcmp({probes.location}, locations{i});
        locTotals(i) = sum(idx);
        
        if locTotals(i) > 0
            locProbes = probes(idx);
            rateMatrix(i, 1) = sum(strcmp({locProbes.probe_outcome}, 'Survived')) / locTotals(i) * 100;
            rateMatrix(i, 2) = sum(strcmp({locProbes.probe_outcome}, 'Dirty Kill')) / locTotals(i) * 100;
            rateMatrix(i, 3) = sum(strcmp({locProbes.probe_outcome}, 'Clean Kill')) / locTotals(i) * 100;
        end
    end
    
    bA2 = bar(axA2, 1:length(locations), rateMatrix, 'grouped', 'EdgeColor', 'none');
    bA2(1).FaceColor = colorSurvive; bA2(2).FaceColor = colorDirty; bA2(3).FaceColor = colorClean; 
    
    % Add N counts directly above the group of bars
    for i = 1:length(locations)
        text(axA2, i, 103, sprintf('N=%d', locTotals(i)), 'HorizontalAlignment', 'center', ...
            'FontSize', 10, 'Color', [0.2 0.2 0.2], 'FontWeight', 'normal');
    end
    
    set(axA2, 'XTick', 1:length(locations), 'XTickLabel', locations);
    legend(axA2, 'Survival Rate (%)', 'Dirty Kill Rate (%)', 'Clean Kill Rate (%)', 'Location', 'northoutside', 'Orientation', 'horizontal', 'Box', 'off');
    ylabel(axA2, 'Relative Outcome Rate (%)', 'FontSize', 12, 'FontWeight', 'normal');
    xlabel(axA2, 'Code Injection Location', 'FontSize', 12, 'FontWeight', 'normal');
    title(axA2, 'Vulnerability Location', 'FontSize', 14, 'FontWeight', 'normal');
    ylim(axA2, [0 115]); 
    applyAcademicStyle(axA2);

    % =====================================================================
    % ANALYSIS 3: The Illusion of Coverage (Binned Trend Chart)
    % =====================================================================
    figA3 = figure('Name', 'Illusion of Coverage', 'Color', 'w', 'Position', [300, 200, 850, 550]);
    axA3 = axes(figA3);
    
    uniqueTestsHit = [probes.unique_tests_hit];
    outcomes = {probes.probe_outcome};
    
    edges = [0, 1, 5, 10, 50, inf];
    binLabels = {'1 Test', '2-5 Tests', '6-10 Tests', '11-50 Tests', '>50 Tests'};
    binIndices = discretize(uniqueTestsHit, edges);
    
    numBins = length(binLabels);
    cleanRates = nan(1, numBins);
    binCounts = zeros(1, numBins);
    
    for i = 1:numBins
        idx = (binIndices == i);
        binCounts(i) = sum(idx);
        if binCounts(i) > 0
            cleanRates(i) = (sum(strcmp(outcomes(idx), 'Clean Kill')) / binCounts(i)) * 100;
        end
    end
    
    validBins = ~isnan(cleanRates);
    x_valid = find(validBins);
    
    plot(axA3, x_valid, cleanRates(validBins), '-o', 'LineWidth', 2.0, 'MarkerSize', 8, ...
         'MarkerFaceColor', colorClean, 'Color', [0.2 0.6 0.4]);
    
    for i = 1:length(x_valid)
        idx = x_valid(i);
        text(axA3, idx, cleanRates(idx) + 4, sprintf('N=%d', binCounts(idx)), ...
            'HorizontalAlignment', 'center', 'FontSize', 10, 'FontWeight', 'normal');
    end
    
    set(axA3, 'XTick', 1:numBins, 'XTickLabel', binLabels);
    xlim(axA3, [0.5 numBins+0.5]);
    ylim(axA3, [0 max(cleanRates(validBins))+20]); 
    ylabel(axA3, 'Probability of a Clean Kill (%)', 'FontSize', 12, 'FontWeight', 'normal');
    xlabel(axA3, 'Number of Tests Hitting the Probe', 'FontSize', 12, 'FontWeight', 'normal');
    title(axA3, 'The Illusion of Coverage', 'FontSize', 14, 'FontWeight', 'normal');
    applyAcademicStyle(axA3);

    % =====================================================================
    % ANALYSIS 4: Triage Compression Ratio
    % =====================================================================
    figA4 = figure('Name', 'Triage Compression Ratio', 'Color', 'w', 'Position', [350, 230, 850, 550]);
    axA4 = axes(figA4);
    
    projects = unique({probes.project});
    numProj = length(projects);
    triageData = zeros(numProj, 3); 
    
    for i = 1:numProj
        projProbes = probes(strcmp({probes.project}, projects{i}));
        projExecs = executions(strcmp({executions.project}, projects{i}));
        
        triageData(i, 1) = sum(strcmp({projExecs.test_outcome}, 'PASS'));
        triageData(i, 2) = length(projProbes);
        triageData(i, 3) = sum(strcmp({projProbes.probe_outcome}, 'Survived'));
    end
    
    bA4 = bar(axA4, 1:numProj, triageData, 'grouped', 'EdgeColor', 'none');
    bA4(1).FaceColor = [0.8 0.8 0.8]; bA4(2).FaceColor = colorNeutral; bA4(3).FaceColor = colorSurvive;  
    
    set(axA4, 'YScale', 'log'); 
    set(axA4, 'XTick', 1:numProj, 'XTickLabel', projects);
    legend(axA4, 'Raw Passed Executions', 'Total Probes Injected', 'Unique Survived Probes', ...
        'Location', 'northoutside', 'Orientation', 'horizontal', 'Box', 'off');
    ylabel(axA4, 'Count (Logarithmic Scale)', 'FontSize', 12, 'FontWeight', 'normal');
    xlabel(axA4, 'Project', 'FontSize', 12, 'FontWeight', 'normal');
    title(axA4, 'Triage Compression Ratio', 'FontSize', 14, 'FontWeight', 'normal');
    
    for i = 1:numProj
        if triageData(i, 1) > 0 && triageData(i, 3) > 0
            ratio = (1 - (triageData(i, 3) / triageData(i, 1))) * 100;
            text(axA4, i, triageData(i, 3) * 1.5, sprintf('%.1f%% Compression\n(N=%d -> N=%d)', ratio, triageData(i, 1), triageData(i, 3)), ...
                'HorizontalAlignment', 'center', 'VerticalAlignment', 'bottom', ...
                'FontSize', 10, 'Color', colorSurvive, 'FontWeight', 'normal');
        end
    end
    applyAcademicStyle(axA4);

    % =====================================================================
    % ANALYSIS 5: Statistical Distribution of Coverage per Outcome
    % =====================================================================
    figA5 = figure('Name', 'Coverage Distribution', 'Color', 'w', 'Position', [400, 260, 850, 550]);
    axA5 = axes(figA5);
    
    outcomeCategorical = categorical({probes.probe_outcome}, {'Survived', 'Clean Kill', 'Dirty Kill'});
    boxA5 = boxchart(axA5, outcomeCategorical, [probes.unique_tests_hit], 'BoxFaceColor', colorNeutral, 'MarkerStyle', 'x');
    
    ylabel(axA5, 'Unique Tests Hitting Probe', 'FontSize', 12, 'FontWeight', 'normal');
    xlabel(axA5, 'Final Probe Outcome', 'FontSize', 12, 'FontWeight', 'normal');
    title(axA5, 'Test Coverage Distribution per Outcome', 'FontSize', 14, 'FontWeight', 'normal');
    
    % Inline N counts to avoid multiple lines under the graph
    survN = sum(outcomeCategorical == 'Survived');
    cleanN = sum(outcomeCategorical == 'Clean Kill');
    dirtyN = sum(outcomeCategorical == 'Dirty Kill');
    set(axA5, 'XTickLabel', {sprintf('Survived (N=%d)', survN), ...
                             sprintf('Clean Kill (N=%d)', cleanN), ...
                             sprintf('Dirty Kill (N=%d)', dirtyN)});
    
    if max([probes.unique_tests_hit]) > 50
        set(axA5, 'YScale', 'log');
        ylabel(axA5, 'Unique Tests Hitting Probe (Log Scale)', 'FontSize', 12, 'FontWeight', 'normal');
    end
    applyAcademicStyle(axA5);

    % =====================================================================
    % ANALYSIS 6: Cross-Project Outcome Comparison
    % =====================================================================
    figA6 = figure('Name', 'Cross-Project Comparison', 'Color', 'w', 'Position', [450, 290, 850, 550]);
    axA6 = axes(figA6);
    
    projOutcomes = zeros(numProj, 3);
    projTotals = zeros(numProj, 1);
    
    for i = 1:numProj
        projProbes = probes(strcmp({probes.project}, projects{i}));
        projTotals(i) = length(projProbes);
        projOutcomes(i, 1) = sum(strcmp({projProbes.probe_outcome}, 'Clean Kill'));
        projOutcomes(i, 2) = sum(strcmp({projProbes.probe_outcome}, 'Dirty Kill'));
        projOutcomes(i, 3) = sum(strcmp({projProbes.probe_outcome}, 'Survived'));
    end
    
    projPercents = (projOutcomes ./ projTotals) * 100;
    
    bA6 = bar(axA6, 1:numProj, projPercents, 'stacked', 'EdgeColor', 'none');
    bA6(1).FaceColor = colorClean; bA6(2).FaceColor = colorDirty; bA6(3).FaceColor = colorSurvive;
    
    for i = 1:numProj
        text(axA6, i, 103, sprintf('N=%d', projTotals(i)), 'HorizontalAlignment', 'center', ...
            'FontSize', 10, 'FontWeight', 'normal');
    end
    
    set(axA6, 'XTick', 1:numProj, 'XTickLabel', projects);
    legend(axA6, 'Clean Kill', 'Dirty Kill', 'Survived', 'Location', 'southoutside', 'Orientation', 'horizontal', 'Box', 'off');
    ylabel(axA6, 'Proportion of Total Probes (%)', 'FontSize', 12, 'FontWeight', 'normal');
    xlabel(axA6, 'Project', 'FontSize', 12, 'FontWeight', 'normal');
    title(axA6, 'Cross-Project Outcome Comparison', 'FontSize', 14, 'FontWeight', 'normal');
    ylim(axA6, [0 115]);
    applyAcademicStyle(axA6);

    disp('Successfully generated 8 refined, thesis-ready analysis figures.');
end