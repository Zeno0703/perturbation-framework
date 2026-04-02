package org.agent;

import org.instrumentation.InstrumentationInstaller;
import org.registry.ProbeCatalog;
import org.runtime.ProbeExecutionTracker;
import org.runtime.TestOutcomeTracker;

import java.lang.instrument.Instrumentation;
import java.nio.file.Files;

public class PerturbationAgent {

    public static void premain(String agentArgs, Instrumentation inst) {
        try {
            Files.createDirectories(AgentConfig.OUT_DIR);
        } catch (Exception ignored) {}

        TestOutcomeTracker.clear();
        ProbeExecutionTracker.clear();
        InstrumentationInstaller.install(inst);

        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            ProbeCatalog.freeze();
            ReportOrchestrator.generateAllReports(AgentConfig.OUT_DIR);
        }));
    }
}