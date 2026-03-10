package org.tracking;

import org.utils.StringUtils;

public class TestContext {

    private static final ThreadLocal<String> current = new InheritableThreadLocal<>();
    private static volatile String globalFallback = null;

    public static void enter(String id) {
        String sanitized = StringUtils.sanitize(id);
        current.set(sanitized);
        globalFallback = sanitized;
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