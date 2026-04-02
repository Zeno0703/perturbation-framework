package org.agent;

import java.nio.file.Path;

public class AgentConfig {
    public static final String OUT_DIR_STR = System.getProperty("perturb.outDir", "target/perturb");
    public static final Path OUT_DIR = Path.of(OUT_DIR_STR);
    public static final String TARGET_PACKAGE = System.getProperty("perturb.package", "");
}