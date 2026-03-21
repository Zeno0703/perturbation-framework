import os
import javalang


def generate_signature_map(project_dir):
    src_dir = os.path.join(project_dir, "src", "main", "java")

    # NEW: Save into the target/perturb directory so Maven ignores it
    out_dir = os.path.join(project_dir, "target", "perturb")
    os.makedirs(out_dir, exist_ok=True)
    output_file = os.path.join(out_dir, "method_lines.properties")

    lines_written = 0

    if not os.path.exists(src_dir):
        return

    with open(output_file, 'w', encoding='utf-8') as out_file:
        for root, _, files in os.walk(src_dir):
            for file in files:
                if file.endswith(".java"):
                    path = os.path.join(root, file)
                    with open(path, 'r', encoding='utf-8') as f:
                        source = f.read()

                    try:
                        tree = javalang.parse.parse(source)
                        package_name = tree.package.name if tree.package else ""

                        for path_node, node in tree.filter(javalang.tree.ClassDeclaration):
                            class_name = node.name
                            fqcn = f"{package_name}.{class_name}" if package_name else class_name

                            for method in node.methods + node.constructors:
                                method_name = method.name if isinstance(method, javalang.tree.MethodDeclaration) else "<init>"
                                arg_count = len(method.parameters)

                                key = f"{fqcn}.{method_name}.{arg_count}"
                                if method.position:
                                    out_file.write(f"{key}={method.position.line}\n")
                                    lines_written += 1

                    except Exception:
                        pass

    print(f"  -> Pre-flight: Mapped {lines_written} exact method signatures.")