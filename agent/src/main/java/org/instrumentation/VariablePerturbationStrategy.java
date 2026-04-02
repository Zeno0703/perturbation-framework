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

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import static net.bytebuddy.matcher.ElementMatchers.any;

public class VariablePerturbationStrategy implements PerturbationStrategy {

    public VariablePerturbationStrategy() {}

    @Override
    public DynamicType.Builder<?> apply(DynamicType.Builder<?> builder, TypeDescription typeDesc, ClassLoader classLoader, Map<String, AsmMethodAnalyser.MethodLineInfo> lineInfoMap) {
        return builder.visit(
                new AsmVisitorWrapper.ForDeclaredMethods()
                        .invokable(any(), new VariableAssignmentPerturber())
                        .writerFlags(net.bytebuddy.jar.asm.ClassWriter.COMPUTE_FRAMES)
        );
    }

    public static class VariableAssignmentPerturber implements AsmVisitorWrapper.ForDeclaredMethods.MethodVisitorWrapper {
        @Override
        public MethodVisitor wrap(TypeDescription instrumentedType,
                                  MethodDescription instrumentedMethod,
                                  MethodVisitor methodVisitor,
                                  Implementation.Context implementationContext,
                                  TypePool typePool,
                                  int writerFlags,
                                  int readerFlags) {

            if (!InstrumentationFilters.isTargetMethod(instrumentedMethod, instrumentedType)) {
                return methodVisitor;
            }

            String asmDesc = instrumentedMethod.getDescriptor();
            return new VariablePerturbationVisitor(Opcodes.ASM9, methodVisitor, instrumentedMethod.toString(), asmDesc);
        }
    }

    public static class VariablePerturbationVisitor extends MethodVisitor {
        private final String methodName;
        private final String asmDesc;
        private final List<PendingProbe> pendingProbes = new ArrayList<>();
        private final Map<Integer, LvtData> lvtEntries = new HashMap<>();
        private int currentLine = -1;

        public VariablePerturbationVisitor(int api, MethodVisitor methodVisitor, String methodName, String asmDesc) {
            super(api, methodVisitor);
            this.methodName = methodName;
            this.asmDesc = asmDesc;
        }

        @Override
        public void visitLineNumber(int line, Label start) {
            currentLine = line;
            super.visitLineNumber(line, start);
        }

        @Override
        public void visitVarInsn(int opcode, int varIndex) {
            if (opcode == Opcodes.ISTORE) {
                int probeId = ProbeRegistrar.registerVariable(methodName, varIndex, currentLine, asmDesc, "Integer/Boolean", false);
                pendingProbes.add(new PendingProbe(probeId, varIndex));

                super.visitLdcInsn(probeId);
                super.visitMethodInsn(Opcodes.INVOKESTATIC, "org/probe/PerturbationGate", "apply", "(II)I", false);

            } else if (opcode == Opcodes.ASTORE) {
                int probeId = ProbeRegistrar.registerVariable(methodName, varIndex, currentLine, asmDesc, "Object", true);
                pendingProbes.add(new PendingProbe(probeId, varIndex));

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
            int probeId = ProbeRegistrar.registerVariable(methodName, varIndex, currentLine, asmDesc, "Integer", false);
            pendingProbes.add(new PendingProbe(probeId, varIndex));

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
                String type = ProbeRegistrar.resolveTypeName(descriptor);
                if (!type.equals("Object") || descriptor.startsWith("[") || descriptor.startsWith("L")) {
                    lvtEntries.putIfAbsent(index, new LvtData(name, type));
                }
            }
            super.visitLocalVariable(name, descriptor, signature, start, end, index);
        }

        @Override
        public void visitEnd() {
            if (!lvtEntries.isEmpty()) {
                for (PendingProbe p : pendingProbes) {
                    if (lvtEntries.containsKey(p.slot)) {
                        LvtData data = lvtEntries.get(p.slot);
                        ProbeRegistrar.updateVariableDescription(p.id, methodName, data.name, data.type);
                    }
                }
            }
            super.visitEnd();
        }

        private record PendingProbe(int id, int slot) {}
        private record LvtData(String name, String type) {}
    }
}