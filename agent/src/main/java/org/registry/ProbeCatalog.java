package org.registry;

import org.utils.FileUtils;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

import static org.utils.JsonUtils.jsonString;

public class ProbeCatalog {

    private static final Map<String, Integer> locations = new ConcurrentHashMap<>();
    private static final Map<Integer, String> reverseLocations = new ConcurrentHashMap<>();
    private static final Map<Integer, String> descriptions = new ConcurrentHashMap<>();
    private static final Map<Integer, String> descriptors = new ConcurrentHashMap<>();
    private static final Map<Integer, Integer> lineNumbers = new ConcurrentHashMap<>();
    private static final Set<Integer> probes = ConcurrentHashMap.newKeySet();
    private static volatile boolean frozen = false;

    public static int idForLocation(String locationKey) {
        if (frozen) {
            return locations.getOrDefault(locationKey, -1);
        }

        return locations.computeIfAbsent(locationKey, key -> {
            int attempt = 0;
            int id;

            while (true) {
                String stringToHash = (attempt == 0) ? key : key + "_coll_" + attempt;
                id = generateDeterministicId(stringToHash);

                String existingKey = reverseLocations.putIfAbsent(id, key);
                if (existingKey == null || existingKey.equals(key)) {
                    break;
                }
                attempt++;
            }
            probes.add(id);
            return id;
        });
    }

    private static int generateDeterministicId(String key) {
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            byte[] hash = md.digest(key.getBytes(StandardCharsets.UTF_8));
            int result = 0;
            for (int i = 0; i < 4; i++) {
                result <<= 8;
                result |= (hash[i] & 0xFF);
            }
            return result & 0x7fffffff;
        } catch (NoSuchAlgorithmException e) {
            return key.hashCode() & 0x7fffffff;
        }
    }

    public static void freeze() {
        frozen = true;
    }

    public static Set<Integer> allProbeIds() {
        return Set.copyOf(probes);
    }

    public static void describe(int probeId, String description) {
        if (frozen) return;
        descriptions.put(probeId, description);
    }

    public static String descriptionFor(int probeId) {
        return descriptions.getOrDefault(probeId, "probe " + probeId);
    }

    public static void setDescriptor(int probeId, String descriptor) {
        if (frozen) return;
        if (descriptor != null) descriptors.put(probeId, descriptor);
    }

    public static String descriptorFor(int probeId) {
        return descriptors.getOrDefault(probeId, "");
    }

    public static void setLine(int probeId, int line) {
        if (frozen) return;
        if (line > 0) lineNumbers.put(probeId, line);
    }

    public static int lineFor(int probeId) {
        return lineNumbers.getOrDefault(probeId, -1);
    }

    public static void dumpTo(Path outDir) throws IOException {
        StringBuilder sb = new StringBuilder();
        for (int id : allProbeIds()) {
            sb.append("{\"id\":")
                    .append(id)
                    .append(",\"description\":")
                    .append(jsonString(descriptionFor(id)))
                    .append(",\"line\":")
                    .append(lineFor(id))
                    .append(",\"asmDescriptor\":")
                    .append(jsonString(descriptorFor(id)))
                    .append("}\n");
        }
        FileUtils.writeAtomic(outDir.resolve("probes.txt"), sb.toString());
    }
}