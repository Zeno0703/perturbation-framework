package org.runtime;

public class TestContext {

    private static final ThreadLocal<String> current = new InheritableThreadLocal<>();

    public static void enter(String id) {
        current.set(id);
    }

    public static String getCurrent() {
        return current.get();
    }

    public static void exit() {
        current.remove();
    }
}