import os
import ast
import astor

scraper_dir = "/Users/hipoglisemi/Desktop/kartavantaj-scraper/src/scrapers"

class ScraperFixer(ast.NodeTransformer):
    def visit_FunctionDef(self, node):
        if node.name in ['run', '_process_source', 'main']:
            # 1. Ensure total_revived = 0 is at the top of the function
            has_init = any(isinstance(stmt, ast.Assign) and 
                          any(isinstance(t, ast.Name) and t.id == 'total_revived' for t in stmt.targets)
                          for stmt in node.body)
            
            if not has_init:
                # Find a good place to insert (after existing counters)
                insert_pos = 0
                for i, stmt in enumerate(node.body):
                    if isinstance(stmt, ast.Assign) and any(isinstance(t, ast.Name) and t.id in ['success', 'saved', 'success_count', 'skipped_count'] for t in stmt.targets):
                        insert_pos = i + 1
                
                node.body.insert(insert_pos, ast.Assign(targets=[ast.Name(id='total_revived', ctx=ast.Store())], value=ast.Constant(value=0)))

            # 2. Fix the loop logic
            for stmt in node.body:
                if isinstance(stmt, (ast.For, ast.While)):
                    self._fix_loop(stmt)
                    
            # 3. Fix log_scraper_execution call
            self._fix_log_call(node)
            
        return self.generic_visit(node)

    def _fix_loop(self, loop_node):
        for stmt in loop_node.body:
            if isinstance(stmt, ast.Try):
                for t_stmt in stmt.body:
                    if isinstance(t_stmt, ast.If) and self._is_res_check(t_stmt):
                        self._add_revived_to_if(t_stmt)
            elif isinstance(stmt, ast.If) and self._is_res_check(stmt):
                self._add_revived_to_if(stmt)

    def _is_res_check(self, if_node):
        # Checks if it's 'if res == "saved":'
        if isinstance(if_node.test, ast.Compare):
            left = if_node.test.left
            if isinstance(left, ast.Name) and left.id in ['res', 'result', 'status']:
                return True
        return False

    def _add_revived_to_if(self, if_node):
        # Check if already has revived
        has_revived = False
        curr = if_node
        while isinstance(curr, ast.If):
            if isinstance(curr.test, ast.Compare) and isinstance(curr.test.comparators[0], ast.Constant) and curr.test.comparators[0].value == 'revived':
                has_revived = True
                break
            if not curr.orelse or not isinstance(curr.orelse[0], ast.If):
                break
            curr = curr.orelse[0]
            
        if not has_revived:
            # Add elif res == "revived": total_revived += 1
            res_var = if_node.test.left.id
            new_if = ast.If(
                test=ast.Compare(left=ast.Name(id=res_var, ctx=ast.Load()), ops=[ast.Eq()], comparators=[ast.Constant(value='revived')]),
                body=[ast.AugAssign(target=ast.Name(id='total_revived', ctx=ast.Store()), op=ast.Add(), value=ast.Constant(value=1))],
                orelse=if_node.orelse
            )
            if_node.orelse = [new_if]

    def _fix_log_call(self, node):
        for stmt in ast.walk(node):
            if isinstance(stmt, ast.Call) and isinstance(stmt.func, ast.Name) and stmt.func.id == 'log_scraper_execution':
                if not any(kw.arg == 'total_revived' for kw in stmt.keywords):
                    stmt.keywords.append(ast.keyword(arg='total_revived', value=ast.Name(id='total_revived', ctx=ast.Load())))

for filename in os.listdir(scraper_dir):
    if not filename.endswith(".py"): continue
    if filename in ["__init__.py", "akbank_base.py"]: continue
    
    filepath = os.path.join(scraper_dir, filename)
    with open(filepath, "r", encoding="utf-8") as f:
        try:
            tree = ast.parse(f.read())
        except Exception as e:
            print(f"❌ Syntax Error in {filename}: {e}")
            continue
    
    fixer = ScraperFixer()
    fixed_tree = fixer.visit(tree)
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(astor.to_source(fixed_tree))
    print(f"✅ AST Fixed: {filename}")
