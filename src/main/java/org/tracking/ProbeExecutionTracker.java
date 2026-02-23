package org.tracking;

import org.utils.FileUtils;

import java.io.IOException;
import java.nio.file.Path;
import java.util.Collections;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

public final class ProbeExecutionTracker {

    private static final Map<String, Set<Integer>> hits = new ConcurrentHashMap<>();

    public static void record(String testId, int probeId) {
        hits.computeIfAbsent(testId, k -> Collections.synchronizedSet(new HashSet<>())).add(probeId);
    }

    public static void clear() {
        hits.clear();
    }

    public static void dumpTo(Path file) throws IOException {
        StringBuilder sb = new StringBuilder();
        for (Map.Entry<String, Set<Integer>> e : hits.entrySet()) {
            String testId = e.getKey();
            for (Integer probeId : e.getValue()) {
                sb.append(probeId).append("\t").append(testId).append("\n");
            }
        }
        FileUtils.writeAtomic(file, sb.toString());
    }
}