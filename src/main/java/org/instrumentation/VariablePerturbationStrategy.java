package org.instrumentation;

import net.bytebuddy.asm.AsmVisitorWrapper;
import net.bytebuddy.description.method.MethodDescription;
import net.bytebuddy.description.type.TypeDescription;
import net.bytebuddy.dynamic.DynamicType;
import net.bytebuddy.implementation.Implementation;
import net.bytebuddy.jar.asm.Label;
import net.bytebuddy.jar.asm.MethodVisitor;
import net.bytebuddy.jar.asm.Opcodes;
import net.bytebuddy.pool.TypePool;
import org.probe.ProbeCatalog;
import java.util.*;

import static net.bytebuddy.matcher.ElementMatchers.any;

public class VariablePerturbationStrategy implements PerturbationStrategy {

    @Override
    public DynamicType.Builder<?> apply(DynamicType.Builder<?> builder) {
        return builder.visit(
                new AsmVisitorWrapper.ForDeclaredMethods()
                        .method(any(), new VariableAssignmentPerturber())
                        .writerFlags(net.bytebuddy.jar.asm.ClassWriter.COMPUTE_FRAMES)
        );
    }

    public static class VariableAssignmentPerturber implements AsmVisitorWrapper.ForDeclaredMethods.MethodVisitorWrapper {
        @Override
        public MethodVisitor wrap(TypeDescription instrumentedType, MethodDescription instrumentedMethod, MethodVisitor methodVisitor, Implementation.Context implementationContext, TypePool typePool, int writerFlags, int readerFlags) {
            if (instrumentedMethod.isSynthetic() || instrumentedMethod.isBridge() || instrumentedMethod.getName().contains("$")) {
                return methodVisitor;
            }
            return new VariablePerturbationVisitor(Opcodes.ASM9, methodVisitor, instrumentedMethod.toString());
        }
    }

    public static class VariablePerturbationVisitor extends MethodVisitor {
        private final String methodName;
        private final List<PendingProbe> pendingProbes = new ArrayList<>();
        private final Map<Integer, LvtData> lvtEntries = new HashMap<>();
        private int currentLine = -1;

        public VariablePerturbationVisitor(int api, MethodVisitor methodVisitor, String methodName) {
            super(api, methodVisitor);
            this.methodName = methodName;
        }

        @Override
        public void visitLineNumber(int line, Label start) {
            currentLine = line;
            super.visitLineNumber(line, start);
        }

        @Override
        public void visitVarInsn(int opcode, int varIndex) {
            if (opcode == Opcodes.ISTORE) {
                int probeId = ProbeCatalog.idForLocation(methodName + ":var:" + varIndex);
                ProbeCatalog.setLine(probeId, currentLine);
                pendingProbes.add(new PendingProbe(probeId, varIndex, "Integer/boolean", false));

                super.visitLdcInsn(probeId);
                super.visitMethodInsn(Opcodes.INVOKESTATIC, "org/probe/PerturbationGate", "apply", "(II)I", false);
            } else if (opcode == Opcodes.ASTORE) {
                int probeId = ProbeCatalog.idForLocation(methodName + ":objVar:" + varIndex);
                ProbeCatalog.setLine(probeId, currentLine);
                pendingProbes.add(new PendingProbe(probeId, varIndex, "Object", false));

                super.visitInsn(Opcodes.DUP);
                super.visitLdcInsn(probeId);
                super.visitMethodInsn(Opcodes.INVOKESTATIC, "org/probe/PerturbationGate", "checkAndTrackObject", "(Ljava/lang/Object;I)Z", false);
                Label skip = new Label();
                super.visitJumpInsn(Opcodes.IFEQ, skip);
                super.visitInsn(Opcodes.POP);
                super.visitInsn(Opcodes.ACONST_NULL);
                super.visitLabel(skip);
            }
            super.visitVarInsn(opcode, varIndex);
        }

        @Override
        public void visitIincInsn(int varIndex, int increment) {
            int probeId = ProbeCatalog.idForLocation(methodName + ":var:" + varIndex);
            ProbeCatalog.setLine(probeId, currentLine);
            pendingProbes.add(new PendingProbe(probeId, varIndex, "Integer", true));

            super.visitVarInsn(Opcodes.ILOAD, varIndex);
            super.visitIntInsn(Opcodes.SIPUSH, increment);
            super.visitInsn(Opcodes.IADD);
            super.visitLdcInsn(probeId);
            super.visitMethodInsn(Opcodes.INVOKESTATIC, "org/probe/PerturbationGate", "apply", "(II)I", false);
            super.visitVarInsn(Opcodes.ISTORE, varIndex);
        }

        @Override
        public void visitLocalVariable(String name, String descriptor, String signature, Label start, Label end, int index) {
            if (!name.equals("this") && !name.startsWith("this$")) {
                String type = "unknown";
                if (descriptor.equals("Z")) type = "boolean";
                else if (descriptor.equals("I") || descriptor.equals("S") || descriptor.equals("B") || descriptor.equals("C")) type = "Integer";
                else if (descriptor.startsWith("[") || descriptor.startsWith("L")) type = "Object";

                if (!type.equals("unknown")) {
                    lvtEntries.putIfAbsent(index, new LvtData(name, type));
                }
            }
            super.visitLocalVariable(name, descriptor, signature, start, end, index);
        }

        @Override
        public void visitEnd() {
            // Filter based on LVT presence
            boolean lvtPresent = !lvtEntries.isEmpty();

            for (PendingProbe p : pendingProbes) {
                if (lvtPresent) {
                    if (lvtEntries.containsKey(p.slot)) {
                        LvtData data = lvtEntries.get(p.slot);
                        ProbeCatalog.describe(p.id, "Modified " + data.type + " local variable '" + data.name + "' in " + methodName);
                    }
                } else {
                    ProbeCatalog.describe(p.id, "Modified " + p.fallbackType + " local variable (JVM slot " + p.slot + ") in " + methodName);
                }
            }
            super.visitEnd();
        }

        private static class PendingProbe {
            final int id, slot;
            final String fallbackType;
            final boolean isIinc;
            PendingProbe(int id, int slot, String type, boolean iinc) { this.id = id; this.slot = slot; this.fallbackType = type; this.isIinc = iinc; }
        }

        private static class LvtData {
            final String name, type;
            LvtData(String name, String type) { this.name = name; this.type = type; }
        }
    }
}