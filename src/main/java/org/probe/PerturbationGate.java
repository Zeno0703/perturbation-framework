package org.probe;

import org.tracking.ProbeExecutionTracker;
import org.tracking.TestContext;

public class PerturbationGate {

    public static int apply(int value, int probeId) {
        String testId = track(probeId);
        if (PerturbationController.isActive(probeId)) {
            int newValue = value + 1;
            ProbeExecutionTracker.recordAction(testId, value, newValue);
            return newValue;
        }
        return value;
    }

    public static boolean apply(boolean value, int probeId) {
        String testId = track(probeId);
        if (PerturbationController.isActive(probeId)) {
            boolean newValue = !value;
            ProbeExecutionTracker.recordAction(testId, value, newValue);
            return newValue;
        }
        return value;
    }

    public static Object apply(Object value, int probeId) {
        String testId = track(probeId);
        if (PerturbationController.isActive(probeId)) {
            ProbeExecutionTracker.recordAction(testId, value, "null");
            return null;
        }
        return value;
    }

    public static boolean checkAndTrackObject(Object value, int probeId) {
        String testId = track(probeId);
        if (PerturbationController.isActive(probeId)) {
            ProbeExecutionTracker.recordAction(testId, value, "null");
            return true;
        }
        return false;
    }

    private static String track(int probeId) {
        String test = TestContext.getCurrent();
        if (test != null) {
            ProbeExecutionTracker.record(test, probeId);
            return test;
        }
        return "UNKNOWN_TEST";
    }
}