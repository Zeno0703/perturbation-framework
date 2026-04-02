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
        TestContext.enter(stableId(context));
    }

    @Override
    public void afterEach(ExtensionContext context) {
        TestContext.exit();
        ReportOrchestrator.generateAllReports(AgentConfig.OUT_DIR);
    }

    @Override
    public void testSuccessful(ExtensionContext context) {
        TestOutcomeTracker.pass(stableId(context));
    }

    @Override
    public void testFailed(ExtensionContext context, Throwable cause) {
        TestOutcomeTracker.fail(stableId(context), cause);
    }

    private static String stableId(ExtensionContext context) {
        return context.getRequiredTestClass().getName() + "#" + context.getRequiredTestMethod().getName();
    }
}