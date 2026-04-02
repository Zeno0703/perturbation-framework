package org.tracking;

import org.probe.ProbeCatalog;
import java.nio.file.Path;

public class ReportManager {

    public static void generateAllReports(Path outDir) {
        dumpQuietly(() -> ProbeCatalog.dumpTo(outDir), "probes");
        dumpQuietly(() -> ProbeExecutionTracker.dumpTo(outDir), "execution tracker");
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