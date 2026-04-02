package org.instrumentation.strategy;

import net.bytebuddy.asm.AsmVisitorWrapper;
import net.bytebuddy.description.method.MethodDescription;
import net.bytebuddy.description.method.ParameterDescription;
import net.bytebuddy.description.type.TypeDescription;
import net.bytebuddy.dynamic.DynamicType;
import net.bytebuddy.implementation.Implementation;
import net.bytebuddy.jar.asm.MethodVisitor;
import net.bytebuddy.jar.asm.Opcodes;
import net.bytebuddy.pool.TypePool;
import org.instrumentation.AsmMethodAnalyser;
import org.instrumentation.InstrumentationFilters;
import org.registry.ProbeRegistrar;

import java.util.Map;

import static net.bytebuddy.matcher.ElementMatchers.any;

public class ArgumentPerturbationStrategy implements PerturbationStrategy {

    @Override
    public DynamicType.Builder<?> apply(DynamicType.Builder<?> builder, TypeDescription typeDesc, ClassLoader classLoader, Map<String, AsmMethodAnalyser.MethodLineInfo> lineInfoMap) {
        return builder.visit(
                new AsmVisitorWrapper.ForDeclaredMethods()
                        .invokable(any(), new ArgumentPerturberWrapper(typeDesc, lineInfoMap))
                        .writerFlags(net.bytebuddy.jar.asm.ClassWriter.COMPUTE_FRAMES)
        );
    }

    public static class ArgumentPerturberWrapper implements AsmVisitorWrapper.ForDeclaredMethods.MethodVisitorWrapper {
        private final TypeDescription typeDesc;
        private final Map<String, AsmMethodAnalyser.MethodLineInfo> lineInfoMap;

        public ArgumentPerturberWrapper(TypeDescription typeDesc, Map<String, AsmMethodAnalyser.MethodLineInfo> lineInfoMap) {
            this.typeDesc = typeDesc;
            this.lineInfoMap = lineInfoMap;
        }

        @Override
        public MethodVisitor wrap(TypeDescription instrumentedType, MethodDescription instrumentedMethod, MethodVisitor methodVisitor, Implementation.Context implementationContext, TypePool typePool, int writerFlags, int readerFlags) {
            if (!InstrumentationFilters.isTargetMethod(instrumentedMethod, instrumentedType)) {
                return methodVisitor;
            }
            return new ArgumentVisitor(Opcodes.ASM9, methodVisitor, instrumentedMethod, typeDesc, lineInfoMap);
        }
    }

    public static class ArgumentVisitor extends MethodVisitor {
        private final MethodDescription method;
        private final TypeDescription typeDesc;
        private final Map<String, AsmMethodAnalyser.MethodLineInfo> lineInfoMap;

        public ArgumentVisitor(int api, MethodVisitor methodVisitor, MethodDescription method, TypeDescription typeDesc, Map<String, AsmMethodAnalyser.MethodLineInfo> lineInfoMap) {
            super(api, methodVisitor);
            this.method = method;
            this.typeDesc = typeDesc;
            this.lineInfoMap = lineInfoMap;
        }

        @Override
        public void visitCode() {
            super.visitCode();

            String locationKey = method.toString();
            String asmDesc = method.getDescriptor();
            String asmName = method.isConstructor() ? "<init>" : method.getInternalName();

            AsmMethodAnalyser.MethodLineInfo info = lineInfoMap.getOrDefault(asmName + asmDesc, new AsmMethodAnalyser.MethodLineInfo());
            int exactLine = ProbeRegistrar.getSignatureLine(typeDesc, method, info.firstLine != -1 ? info.firstLine : 0);

            int currentSlot = method.isStatic() ? 0 : 1;

            for (int i = 0; i < method.getParameters().size(); i++) {
                ParameterDescription param = method.getParameters().get(i);
                TypeDescription.Generic pType = param.getType();

                if (ProbeRegistrar.isSupportedType(pType)) {
                    int probeId = ProbeRegistrar.registerArgument(locationKey, i, exactLine, asmDesc, ProbeRegistrar.resolveTypeName(pType));

                    if (pType.represents(int.class) || pType.represents(short.class) || pType.represents(byte.class) || pType.represents(char.class)) {
                        super.visitVarInsn(Opcodes.ILOAD, currentSlot);
                        super.visitLdcInsn(probeId);
                        super.visitMethodInsn(Opcodes.INVOKESTATIC, PerturbationStrategy.GATE_CLASS, PerturbationStrategy.GATE_METHOD, PerturbationStrategy.DESC_INT, false);

                        if (pType.represents(short.class)) {
                            super.visitInsn(Opcodes.I2S);
                        } else if (pType.represents(byte.class)) {
                            super.visitInsn(Opcodes.I2B);
                        } else if (pType.represents(char.class)) {
                            super.visitInsn(Opcodes.I2C);
                        }

                        super.visitVarInsn(Opcodes.ISTORE, currentSlot);

                    } else if (pType.represents(boolean.class)) {
                        super.visitVarInsn(Opcodes.ILOAD, currentSlot);
                        super.visitLdcInsn(probeId);
                        super.visitMethodInsn(Opcodes.INVOKESTATIC, PerturbationStrategy.GATE_CLASS, PerturbationStrategy.GATE_METHOD, PerturbationStrategy.DESC_BOOL, false);
                        super.visitVarInsn(Opcodes.ISTORE, currentSlot);

                    } else { // Object
                        super.visitVarInsn(Opcodes.ALOAD, currentSlot);
                        super.visitLdcInsn(probeId);
                        super.visitMethodInsn(Opcodes.INVOKESTATIC, PerturbationStrategy.GATE_CLASS, PerturbationStrategy.GATE_METHOD, PerturbationStrategy.DESC_OBJ, false);
                        super.visitTypeInsn(Opcodes.CHECKCAST, pType.asErasure().getInternalName());
                        super.visitVarInsn(Opcodes.ASTORE, currentSlot);
                    }
                }

                currentSlot += pType.getStackSize().getSize();
            }
        }
    }
}