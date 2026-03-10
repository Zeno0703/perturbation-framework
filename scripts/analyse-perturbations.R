library(jsonlite)
library(ggplot2)
library(dplyr)
library(tidyr)
library(scales)
library(forcats)

# =============================================================================
# 1. LOAD AND PREPARE DATA
# =============================================================================
file_name <- "database.json"
if (!file.exists(file_name)) {
  stop("File database.json not found. Please set your working directory to the file's location.")
}

data <- fromJSON(file_name)
probes <- as.data.frame(data$probes)
executions <- as.data.frame(data$test_executions)

# Define standard factor levels so colors map consistently across all plots
outcome_levels <- c("Clean Kill", "Dirty Kill", "Survived")
probes$probe_outcome <- factor(probes$probe_outcome, levels = outcome_levels)

# =============================================================================
# 2. AESTHETICS & THEME SETUP
# =============================================================================
# Thesis-Ready Minimalist Color Palette
colorClean   <- "#2ECC71"  # Emerald Green
colorDirty   <- "#F39C12"  # Sunflower Orange
colorSurvive <- "#E74C3C"  # Alizarin Red
colorNeutral <- "#4C73A6"  # Academic Blue

palette_outcomes <- c("Clean Kill" = colorClean, 
                      "Dirty Kill" = colorDirty, 
                      "Survived" = colorSurvive)

# Custom ggplot theme for thesis (clean white, y-grid only, unbolded text)
theme_academic <- function() {
  theme_minimal(base_family = "sans", base_size = 11) +
    theme(
      plot.title = element_text(size = 14, face = "plain", hjust = 0.5, margin = margin(b = 10)),
      axis.title = element_text(size = 12, face = "plain"),
      axis.text = element_text(size = 10, color = "black"),
      panel.grid.major.x = element_blank(),
      panel.grid.minor.x = element_blank(),
      panel.grid.major.y = element_line(color = "#E0E0E0", size = 0.5),
      panel.grid.minor.y = element_blank(),
      axis.line.x = element_line(color = "black", size = 0.5),
      axis.line.y = element_line(color = "black", size = 0.5),
      legend.position = "bottom",
      legend.title = element_blank(),
      legend.text = element_text(size = 11, face = "plain"),
      plot.background = element_rect(fill = "white", color = NA),
      panel.background = element_rect(fill = "white", color = NA)
    )
}

# =====================================================================
# GENERAL 1: Overall Probe Outcomes
# =====================================================================
df_g1 <- probes %>%
  count(probe_outcome) %>%
  mutate(pct = n / sum(n),
         label = sprintf("N=%d\n(%.1f%%)", n, pct * 100))

g1 <- ggplot(df_g1, aes(x = probe_outcome, y = n, fill = probe_outcome)) +
  geom_col(width = 0.6, show.legend = FALSE) +
  geom_text(aes(label = label, y = n + max(n)*0.05), vjust = 0, size = 4) +
  scale_fill_manual(values = palette_outcomes) +
  scale_y_continuous(expand = expansion(mult = c(0, 0.2))) +
  labs(title = "Overall Probe Outcomes", y = "Total Number of Probes", x = NULL) +
  theme_academic()

print(g1)

# =====================================================================
# GENERAL 2: Test Execution Outcomes Breakdown
# =====================================================================
exec_levels <- c("PASS", "FAIL by Assert", "FAIL by Exception")
df_g2 <- executions %>%
  mutate(test_outcome = factor(test_outcome, levels = exec_levels)) %>%
  count(test_outcome) %>%
  mutate(pct = n / sum(n),
         label = sprintf("N=%d\n(%.1f%%)", n, pct * 100))

# Map PASS->Survive(Red), Assert->Clean(Green), Exception->Dirty(Orange)
palette_exec <- c("PASS" = colorSurvive, "FAIL by Assert" = colorClean, "FAIL by Exception" = colorDirty)

g2 <- ggplot(df_g2, aes(x = test_outcome, y = n, fill = test_outcome)) +
  geom_col(width = 0.6, show.legend = FALSE) +
  geom_text(aes(label = label, y = n + max(n)*0.05), vjust = 0, size = 4) +
  scale_fill_manual(values = palette_exec) +
  scale_y_continuous(expand = expansion(mult = c(0, 0.2))) +
  labs(title = "Test Execution Results", y = "Total Number of Test Executions", x = NULL) +
  theme_academic()

print(g2)

# =====================================================================
# GENERAL 3: Exception Profile (Dirty Kills)
# =====================================================================
df_g3 <- executions %>%
  filter(exception != "none") %>%
  count(exception, sort = TRUE) %>%
  slice_head(n = 8) %>%
  mutate(exception = fct_reorder(exception, n)) # Order for horizontal bar

if(nrow(df_g3) > 0) {
  g3 <- ggplot(df_g3, aes(x = exception, y = n)) +
    geom_col(fill = colorDirty, width = 0.7) +
    geom_text(aes(label = sprintf("N=%d", n), y = n + max(n)*0.02), hjust = 0, size = 3.5) +
    coord_flip() +
    scale_y_continuous(expand = expansion(mult = c(0, 0.15))) +
    labs(title = "Top Exceptions Causing Dirty Kills", y = "Frequency of Exception", x = NULL) +
    theme_academic() +
    theme(panel.grid.major.y = element_blank(), panel.grid.major.x = element_line(color = "#E0E0E0"))
  
  print(g3)
}

# =====================================================================
# ANALYSIS 1: Operator Efficacy (100% Stacked Bar)
# =====================================================================
df_a1_totals <- probes %>% group_by(operator) %>% summarize(total = n())
df_a1 <- probes %>%
  count(operator, probe_outcome) %>%
  group_by(operator) %>%
  mutate(pct = n / sum(n))

g1_a1 <- ggplot(df_a1, aes(x = operator, y = pct, fill = probe_outcome)) +
  geom_col(position = "fill", width = 0.7) +
  geom_text(data = df_a1_totals, aes(x = operator, y = 1.05, label = sprintf("N=%d", total)), 
            inherit.aes = FALSE, size = 3.5, vjust = 0) +
  scale_fill_manual(values = palette_outcomes) +
  scale_y_continuous(labels = percent_format(), expand = expansion(mult = c(0, 0.15))) +
  labs(title = "Operator Efficacy", y = "Proportion of Outcomes", x = "Perturbation Operator") +
  theme_academic() +
  theme(axis.text.x = element_text(angle = 30, hjust = 1))

print(g1_a1)

# =====================================================================
# ANALYSIS 2: Vulnerability Location Rates
# =====================================================================
df_a2 <- probes %>%
  filter(location %in% c("Argument", "Return", "Variable")) %>%
  count(location, probe_outcome) %>%
  group_by(location) %>%
  mutate(rate = (n / sum(n))) %>%
  ungroup()

df_a2_totals <- df_a2 %>% group_by(location) %>% summarize(total = sum(n))

g2_a2 <- ggplot(df_a2, aes(x = location, y = rate, fill = probe_outcome)) +
  geom_col(position = position_dodge(width = 0.8), width = 0.7) +
  geom_text(data = df_a2_totals, aes(x = location, y = 1.05, label = sprintf("N=%d", total)), 
            inherit.aes = FALSE, size = 3.5, vjust = 0) +
  scale_fill_manual(values = palette_outcomes) +
  scale_y_continuous(labels = percent_format(), expand = expansion(mult = c(0, 0.15))) +
  labs(title = "Vulnerability Location", y = "Relative Outcome Rate", x = "Code Injection Location") +
  theme_academic()

print(g2_a2)

# =====================================================================
# ANALYSIS 3: The Illusion of Coverage (Binned Trend Chart)
# =====================================================================
df_a3 <- probes %>%
  mutate(bin = cut(unique_tests_hit, 
                   breaks = c(-Inf, 1, 5, 10, 50, Inf), 
                   labels = c("1 Test", "2-5 Tests", "6-10 Tests", "11-50 Tests", ">50 Tests"))) %>%
  group_by(bin) %>%
  summarize(
    total_in_bin = n(),
    clean_kills = sum(probe_outcome == "Clean Kill"),
    clean_rate = clean_kills / total_in_bin
  ) %>% filter(total_in_bin > 0)

g3_a3 <- ggplot(df_a3, aes(x = bin, y = clean_rate, group = 1)) +
  geom_line(color = "#339966", size = 1.2) +
  geom_point(color = colorClean, size = 4) +
  geom_text(aes(label = sprintf("N=%d", total_in_bin), y = clean_rate + 0.05), size = 3.5) +
  scale_y_continuous(labels = percent_format(), expand = expansion(mult = c(0, 0.15)), limits = c(0,NA)) +
  labs(title = "The Illusion of Coverage", y = "Probability of a Clean Kill", x = "Number of Tests Hitting the Probe") +
  theme_academic()

print(g3_a3)

# =====================================================================
# ANALYSIS 4: Triage Compression Ratio
# =====================================================================
# Calculate data per project
df_a4_probes <- probes %>%
  group_by(project) %>%
  summarize(Total_Probes = n(),
            Unique_Survived = sum(probe_outcome == "Survived"))

df_a4_execs <- executions %>%
  group_by(project) %>%
  summarize(Raw_Passed = sum(test_outcome == "PASS"))

df_a4 <- left_join(df_a4_execs, df_a4_probes, by = "project") %>%
  mutate(Compression = (1 - (Unique_Survived / Raw_Passed)) * 100)

# Reshape data for grouped bar plot
df_a4_long <- df_a4 %>%
  pivot_longer(cols = c(Raw_Passed, Total_Probes, Unique_Survived), 
               names_to = "Metric", values_to = "Count") %>%
  mutate(Metric = factor(Metric, levels = c("Raw_Passed", "Total_Probes", "Unique_Survived"),
                         labels = c("Raw Passed Executions", "Total Probes Injected", "Unique Survived Probes")))

g4_a4 <- ggplot(df_a4_long, aes(x = project, y = Count, fill = Metric)) +
  geom_col(position = position_dodge(width = 0.8), width = 0.7) +
  geom_text(data = df_a4, aes(x = project, y = Unique_Survived * 1.8, 
                              label = sprintf("%.1f%% Compression\n(N=%d -> N=%d)", Compression, Raw_Passed, Unique_Survived)),
            inherit.aes = FALSE, size = 3.5, color = colorSurvive, vjust = 0) +
  scale_fill_manual(values = c("#CCCCCC", colorNeutral, colorSurvive)) +
  scale_y_log10(breaks = trans_breaks("log10", function(x) 10^x),
                labels = trans_format("log10", math_format(10^.x))) +
  labs(title = "Triage Compression Ratio", y = "Count (Logarithmic Scale)", x = "Project") +
  theme_academic()

print(g4_a4)

# =====================================================================
# ANALYSIS 5: Statistical Distribution of Coverage per Outcome
# =====================================================================
df_a5_totals <- probes %>% count(probe_outcome)

g5_a5 <- ggplot(probes, aes(x = probe_outcome, y = unique_tests_hit)) +
  geom_boxplot(fill = colorNeutral, color = "#2C3E50", alpha = 0.7, outlier.shape = 4) +
  scale_x_discrete(labels = function(x) {
    counts <- df_a5_totals$n[match(x, df_a5_totals$probe_outcome)]
    paste0(x, " (N=", counts, ")")
  }) +
  labs(title = "Test Coverage Distribution per Outcome", 
       y = "Unique Tests Hitting Probe", x = "Final Probe Outcome") +
  theme_academic()

# Apply log scale if there are many test hits (prevent squishing)
if(max(probes$unique_tests_hit, na.rm=TRUE) > 50) {
  g5_a5 <- g5_a5 + scale_y_log10() + labs(y = "Unique Tests Hitting Probe (Log Scale)")
}

print(g5_a5)

# =====================================================================
# ANALYSIS 6: Cross-Project Outcome Comparison
# =====================================================================
df_a6_totals <- probes %>% group_by(project) %>% summarize(total = n())
df_a6 <- probes %>%
  count(project, probe_outcome) %>%
  group_by(project) %>%
  mutate(pct = n / sum(n))

g6_a6 <- ggplot(df_a6, aes(x = project, y = pct, fill = probe_outcome)) +
  geom_col(position = "fill", width = 0.6) +
  geom_text(data = df_a6_totals, aes(x = project, y = 1.05, label = sprintf("N=%d", total)), 
            inherit.aes = FALSE, size = 3.5, vjust = 0) +
  scale_fill_manual(values = palette_outcomes) +
  scale_y_continuous(labels = percent_format(), expand = expansion(mult = c(0, 0.15))) +
  labs(title = "Cross-Project Outcome Comparison", y = "Proportion of Total Probes", x = "Project") +
  theme_academic()

print(g6_a6)

cat("\nSuccessfully generated 8 refined, thesis-ready analysis figures in R.\n")