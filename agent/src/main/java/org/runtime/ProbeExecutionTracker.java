package org.runtime;

import org.utils.FileUtils;

import java.io.IOException;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;

import static org.utils.JsonUtils.jsonString;

public class ProbeExecutionTracker {

    private static final Map<String, Set<Integer>> hits = new ConcurrentHashMap<>();
    private static final Queue<ActionRecord> actions = new ConcurrentLinkedQueue<>();

    private record ActionRecord(String testId, String original, String perturbed) {}
    private record HitRecord(String testId, Integer probeId) {}

    public static void record(String testId, int probeId) {
        hits.computeIfAbsent(testId, k -> ConcurrentHashMap.newKeySet()).add(probeId);
    }

    public static void recordAction(String testId, Object original, Object perturbed) {
        String origStr = safeToString(original);
        String pertStr = safeToString(perturbed);
        actions.add(new ActionRecord(testId, origStr, pertStr));
    }

    private static String safeToString(Object obj) {
        if (obj == null) return "null";
        try {
            return String.valueOf(obj);
        } catch (Throwable t) {
            return obj.getClass().getName() + "@" + Integer.toHexString(System.identityHashCode(obj));
        }
    }

    public static void clear() {
        hits.clear();
        actions.clear();
    }

    public static void dumpTo(Path outDir) throws IOException {
        List<HitRecord> flatHits = new ArrayList<>();
        for (Map.Entry<String, Set<Integer>> e : hits.entrySet()) {
            for (Integer probeId : e.getValue()) {
                flatHits.add(new HitRecord(e.getKey(), probeId));
            }
        }

        FileUtils.writeLinesAtomic(
                outDir.resolve("hits.txt"),
                flatHits,
                h -> "{\"probe_id\":" + h.probeId() + ",\"test\":" + jsonString(h.testId()) + "}"
        );

        FileUtils.writeLinesAtomic(
                outDir.resolve("perturbations.txt"),
                actions,
                a -> "{\"test\":" + jsonString(a.testId())
                        + ",\"original\":" + jsonString(a.original())
                        + ",\"perturbed\":" + jsonString(a.perturbed())
                        + "}"
        );
    }
}