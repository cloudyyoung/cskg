import os
from astroid import FunctionDef, Module, ClassDef, NodeNG
from astroid.manager import AstroidManager
from loguru import logger

from cskg.interpreter import remove_module_prefix
from cskg.interpreter.nodes import visit_node


class CodeInterpreter:
    def __init__(self, folder_path):
        self.folder_path = folder_path
        self.manager = AstroidManager()
        self.manager.register_transform(Module, self.format_qname)
        self.manager.register_transform(ClassDef, self.format_qname)
        self.manager.register_transform(FunctionDef, self.format_qname)

    def interpret(self):
        yield from self.traverse_files()

    def traverse_files(self):
        asts = {}

        for root, dirs, files in os.walk(self.folder_path):
            for file in files:
                if file.endswith(".py"):  # Only handles python file
                    file_path = os.path.join(root, file)
                    ast = self.manager.ast_from_file(file_path)
                    asts[file_path] = ast
                    logger.debug(f"Ast from file: {file_path}")

        for file_path, ast in asts.items():
            yield from visit_node(ast)

    def format_qname(self, node: Module | ClassDef | FunctionDef):
        original_qname_function = node.qname
        node.qname = lambda: remove_module_prefix(
            original_qname_function(), self.folder_path
        )
        return node
