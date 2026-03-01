package org.tracking;

import org.utils.StringUtils;

public class TestContext {

    private static final ThreadLocal<String> current = new ThreadLocal<>();

    public static void enter(String id) {
        current.set(StringUtils.sanitize(id));
    }

    public static String getCurrent() {
        return current.get();
    }

    public static void exit() {
        current.remove();
    }
}