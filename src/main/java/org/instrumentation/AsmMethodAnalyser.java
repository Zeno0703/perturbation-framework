package org.instrumentation;

import net.bytebuddy.jar.asm.ClassReader;
import net.bytebuddy.jar.asm.ClassVisitor;
import net.bytebuddy.jar.asm.MethodVisitor;
import net.bytebuddy.jar.asm.Opcodes;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

class AsmMethodAnalyser {

    static class MethodLineInfo {
        int firstLine = -1;
        Set<Integer> returnLines = new HashSet<>();
    }

    static Map<String, MethodLineInfo> analyseClass(ClassLoader loader, String classResourcePath) {
        Map<String, MethodLineInfo> methodMap = new HashMap<>();
        if (loader == null) return methodMap;

        try (var stream = loader.getResourceAsStream(classResourcePath)) {
            if (stream == null) return methodMap;

            new ClassReader(stream).accept(new ClassVisitor(Opcodes.ASM9) {
                @Override
                public MethodVisitor visitMethod(int access, String name, String descriptor, String signature, String[] exceptions) {
                    MethodLineInfo info = new MethodLineInfo();
                    methodMap.put(name + descriptor, info);

                    return new MethodVisitor(Opcodes.ASM9) {
                        int currentLine = -1;
                        @Override
                        public void visitLineNumber(int line, net.bytebuddy.jar.asm.Label start) {
                            if (info.firstLine == -1) info.firstLine = line;
                            currentLine = line;
                        }
                        @Override
                        public void visitInsn(int opcode) {
                            if (opcode >= Opcodes.IRETURN && opcode <= Opcodes.RETURN && currentLine != -1) {
                                info.returnLines.add(currentLine);
                            }
                        }
                    };
                }
            }, ClassReader.SKIP_FRAMES);
        } catch (Exception ignored) {}

        return methodMap;
    }
}