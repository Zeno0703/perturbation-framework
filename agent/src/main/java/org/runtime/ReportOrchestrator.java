package org.runtime;

import org.registry.ProbeCatalog;

import java.nio.file.Path;

public class ReportOrchestrator {

    public static void generateAllReports(Path outDir) {
        dumpQuietly(() -> ProbeCatalog.dumpTo(outDir), "probes");
        dumpQuietly(() -> ProbeExecutionTracker.dumpTo(outDir), "execution tracker");
        dumpQuietly(() -> TestOutcomeTracker.dumpTo(outDir), "test outcomes");
    }

    public static void dumpOutcomesOnly(Path outDir) {
        dumpQuietly(() -> TestOutcomeTracker.dumpTo(outDir), "test outcomes");
    }

    private interface DumpTask { void execute() throws Exception; }

    private static void dumpQuietly(DumpTask task, String name) {
        try {
            task.execute();
        } catch (Exception e) {
            System.err.println("Failed to dump " + name + ": " + e.getMessage());
        }
    }
}