package org.tracking;

public class TestContext {

    private static final ThreadLocal<String> current = new InheritableThreadLocal<>();
    private static volatile String globalFallback = null;

    public static void enter(String id) {
        current.set(id);
        globalFallback = id;
    }

    public static String getCurrent() {
        String local = current.get();
        return local != null ? local : globalFallback;
    }

    public static void exit() {
        current.remove();
        globalFallback = null;
    }
}