package org.runtime;

import org.agent.AgentConfig;

public class PerturbationGate {

    public static int apply(int value, int probeId) {
        try {
            String testId = getTestIdIfActive(probeId);
            if (testId != null) {
                int newValue = value + 1;
                ProbeExecutionTracker.recordAction(testId, value, newValue);
                return newValue;
            }
        } catch (Throwable t) {
            handleError(t, probeId);
        }
        return value;
    }

    public static boolean apply(boolean value, int probeId) {
        try {
            String testId = getTestIdIfActive(probeId);
            if (testId != null) {
                boolean newValue = !value;
                ProbeExecutionTracker.recordAction(testId, value, newValue);
                return newValue;
            }
        } catch (Throwable t) {
            handleError(t, probeId);
        }
        return value;
    }

    public static Object apply(Object value, int probeId) {
        try {
            String testId = getTestIdIfActive(probeId);
            if (testId != null) {
                if (value == null) return null;
                ProbeExecutionTracker.recordAction(testId, value, "null");
                return null;
            }
        } catch (Throwable t) {
            handleError(t, probeId);
        }
        return value;
    }

    public static boolean checkAndTrackObject(Object value, int probeId) {
        try {
            String testId = getTestIdIfActive(probeId);
            if (testId != null) {
                if (value == null) return false;
                ProbeExecutionTracker.recordAction(testId, value, "null");
                return true;
            }
        } catch (Throwable t) {
            handleError(t, probeId);
        }
        return false;
    }

    private static String getTestIdIfActive(int probeId) {
        String test = TestContext.getCurrent();
        String testId = (test != null) ? test : "UNKNOWN_TEST";

        // Track every hit for reporting, even when this probe is not currently active.
        ProbeExecutionTracker.record(testId, probeId);

        // Returning null signals callers to skip perturbation and keep the original value.
        return (probeId == AgentConfig.PROBE_ID) ? testId : null;
    }

    private static void handleError(Throwable t, int probeId) {
        System.err.println("Agent failed at probe " + probeId + ": " + t.getMessage());
    }
}