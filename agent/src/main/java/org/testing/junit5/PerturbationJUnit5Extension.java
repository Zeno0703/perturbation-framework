package org.testing.junit5;

import org.agent.AgentConfig;
import org.agent.ReportOrchestrator;
import org.junit.jupiter.api.extension.AfterEachCallback;
import org.junit.jupiter.api.extension.BeforeEachCallback;
import org.junit.jupiter.api.extension.ExtensionContext;
import org.junit.jupiter.api.extension.TestWatcher;
import org.runtime.TestContext;
import org.runtime.TestOutcomeTracker;

public class PerturbationJUnit5Extension implements BeforeEachCallback, AfterEachCallback, TestWatcher {

    @Override
    public void beforeEach(ExtensionContext context) {
        String id = stableId(context);
        TestContext.enter(id);
        TestOutcomeTracker.start(id);
        ReportOrchestrator.dumpOutcomesOnly(AgentConfig.OUT_DIR);
    }

    @Override
    public void afterEach(ExtensionContext context) {
        TestContext.exit();
    }

    @Override
    public void testSuccessful(ExtensionContext context) {
        TestOutcomeTracker.pass(stableId(context));
        ReportOrchestrator.generateAllReports(AgentConfig.OUT_DIR);
    }

    @Override
    public void testFailed(ExtensionContext context, Throwable cause) {
        TestOutcomeTracker.fail(stableId(context), cause);
        ReportOrchestrator.generateAllReports(AgentConfig.OUT_DIR);
    }

    @Override
    public void testAborted(ExtensionContext context, Throwable cause) {
        TestOutcomeTracker.abort(stableId(context));
        ReportOrchestrator.generateAllReports(AgentConfig.OUT_DIR);
    }

    private static String stableId(ExtensionContext context) {
        return context.getRequiredTestClass().getName() + "#" + context.getRequiredTestMethod().getName();
    }
}