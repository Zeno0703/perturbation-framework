import os
import javalang

def generate_signature_map(project_dir):
    src_dir = os.path.join(project_dir, "src", "main", "java")
    out_dir = os.path.join(project_dir, "target", "perturb")
    os.makedirs(out_dir, exist_ok=True)
    output_file = os.path.join(out_dir, "method_lines.properties")

    lines_written = 0
    failed_files = 0

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

                        anon_counts = {}
                        node_to_fqcn = {}

                        for ast_path, node in tree:
                            if isinstance(node, javalang.tree.CompilationUnit):
                                continue

                            parent_fqcn = package_name
                            for p in reversed(ast_path):
                                if id(p) in node_to_fqcn:
                                    parent_fqcn = node_to_fqcn[id(p)]
                                    break

                            current_fqcn = None

                            if isinstance(node, (javalang.tree.ClassDeclaration, javalang.tree.EnumDeclaration, javalang.tree.InterfaceDeclaration)):
                                class_name = node.name
                                if parent_fqcn and parent_fqcn != package_name:
                                    current_fqcn = f"{parent_fqcn}${class_name}"
                                else:
                                    current_fqcn = f"{package_name}.{class_name}" if package_name else class_name

                                node_to_fqcn[id(node)] = current_fqcn
                                anon_counts[current_fqcn] = 0

                            elif isinstance(node, javalang.tree.EnumConstantDeclaration) and node.body:
                                if parent_fqcn not in anon_counts:
                                    anon_counts[parent_fqcn] = 0
                                anon_counts[parent_fqcn] += 1
                                current_fqcn = f"{parent_fqcn}${anon_counts[parent_fqcn]}"
                                node_to_fqcn[id(node)] = current_fqcn
                                anon_counts[current_fqcn] = 0

                            elif isinstance(node, javalang.tree.ClassCreator) and node.body:
                                if parent_fqcn not in anon_counts:
                                    anon_counts[parent_fqcn] = 0
                                anon_counts[parent_fqcn] += 1
                                current_fqcn = f"{parent_fqcn}${anon_counts[parent_fqcn]}"
                                node_to_fqcn[id(node)] = current_fqcn
                                anon_counts[current_fqcn] = 0

                            if current_fqcn:
                                # GENERIC EXTRACTION (CLASS LEVEL)
                                class_bounds = {}
                                if hasattr(node, 'type_parameters') and node.type_parameters:
                                    for tp in node.type_parameters:
                                        bound_name = "Object"
                                        tb = getattr(tp, 'type_bound', None)
                                        if tb:
                                            # Unwrap if it's a list (javalang inconsistency)
                                            if isinstance(tb, list) and len(tb) > 0:
                                                tb = tb[0]
                                            if hasattr(tb, 'name') and tb.name:
                                                bound_name = tb.name.split('.')[-1]
                                        class_bounds[tp.name] = bound_name

                                methods = []
                                if isinstance(node, (javalang.tree.ClassDeclaration, javalang.tree.EnumDeclaration)):
                                    methods.extend(getattr(node, 'methods', []))
                                    methods.extend(getattr(node, 'constructors', []))
                                elif isinstance(node, (javalang.tree.EnumConstantDeclaration, javalang.tree.ClassCreator)):
                                    if node.body:
                                        for decl in node.body:
                                            if isinstance(decl, (javalang.tree.MethodDeclaration, javalang.tree.ConstructorDeclaration)):
                                                methods.append(decl)

                                for method in methods:
                                    method_name = method.name if isinstance(method, javalang.tree.MethodDeclaration) else "<init>"

                                    # GENERIC EXTRACTION (METHOD LEVEL)
                                    method_bounds = class_bounds.copy()
                                    if hasattr(method, 'type_parameters') and method.type_parameters:
                                        for tp in method.type_parameters:
                                            bound_name = "Object"
                                            tb = getattr(tp, 'type_bound', None)
                                            if tb:
                                                if isinstance(tb, list) and len(tb) > 0:
                                                    tb = tb[0]
                                                if hasattr(tb, 'name') and tb.name:
                                                    bound_name = tb.name.split('.')[-1]
                                            method_bounds[tp.name] = bound_name

                                    param_types = []
                                    for p in method.parameters:
                                        t_name = p.type.name

                                        if t_name in method_bounds:
                                            t_name = method_bounds[t_name]
                                        elif len(t_name) == 1 and t_name.isupper():
                                            t_name = "Object"

                                        t_name = t_name.split('.')[-1]

                                        dims = getattr(p.type, 'dimensions', 0)
                                        dim_count = dims if isinstance(dims, int) else len(dims)
                                        if dim_count > 0: t_name += "[]" * dim_count
                                        if getattr(p, 'varargs', False): t_name += "[]"

                                        param_types.append(t_name)

                                    param_sig = ",".join(param_types)
                                    line_num = method.position.line if method.position else None

                                    if len(method.parameters) > 0 and method.parameters[0].position:
                                        line_num = method.parameters[0].position.line
                                    elif hasattr(method, 'return_type') and method.return_type and method.return_type.position:
                                        line_num = method.return_type.position.line

                                    if line_num:
                                        key = f"{current_fqcn}.{method_name}.{param_sig}"
                                        out_file.write(f"{key}={line_num}\n")
                                        lines_written += 1

                    except Exception as e:
                        print(f"    [WARN] javalang skipped '{file}': {type(e).__name__} - {e}")
                        failed_files += 1

    print(f"Pre-flight: Mapped {lines_written} exact method signatures.")
    if failed_files > 0:
        print(f"Pre-flight: Skipped {failed_files} unparseable files.")