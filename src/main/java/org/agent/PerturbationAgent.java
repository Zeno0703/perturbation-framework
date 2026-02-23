package org.agent;

import org.instrumentation.InstrumentationController;
import org.probe.ProbeCatalog;
import org.tracking.ProbeExecutionTracker;
import org.tracking.TestOutcomeTracker;

import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;

public final class PerturbationAgent {

    public static void premain(String agentArgs, Instrumentation inst) {
        Path outDir = Path.of(System.getProperty("perturb.outDir", "target/perturb"));
        try {
            Files.createDirectories(outDir);
        } catch (Exception ignored) {}

        TestOutcomeTracker.clear();
        ProbeExecutionTracker.clear();
        InstrumentationController.install(inst);

        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            try {
                ProbeCatalog.freeze();
                ProbeCatalog.dumpTo(outDir.resolve("probes.txt"));
            } catch (Exception e) {
                System.out.println("Failed to dump probes: " + e.getMessage());
            }

            try {
                ProbeExecutionTracker.dumpTo(outDir.resolve("hits.txt"));
            } catch (Exception e) {
                System.out.println("Failed to dump hits: " + e.getMessage());
            }

            try {
                TestOutcomeTracker.dumpTo(outDir.resolve("test-outcomes.txt"));
            } catch (Exception e) {
                System.out.println("Failed to dump test outcomes: " + e.getMessage());
            }
        }));
    }
}