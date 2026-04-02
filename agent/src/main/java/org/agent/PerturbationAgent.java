package org.agent;

import org.instrumentation.InstrumentationController;
import org.probe.ProbeCatalog;
import org.tracking.ProbeExecutionTracker;
import org.tracking.ReportManager;
import org.tracking.TestOutcomeTracker;

import java.lang.instrument.Instrumentation;
import java.nio.file.Files;

public class PerturbationAgent {

    public static void premain(String agentArgs, Instrumentation inst) {
        try {
            Files.createDirectories(AgentConfig.OUT_DIR);
        } catch (Exception ignored) {}

        TestOutcomeTracker.clear();
        ProbeExecutionTracker.clear();
        InstrumentationController.install(inst);

        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            ProbeCatalog.freeze();
            ReportManager.generateAllReports(AgentConfig.OUT_DIR);
        }));
    }
}