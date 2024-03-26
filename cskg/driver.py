from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError, InvalidOperation
import neomodel
from neomodel import clear_neo4j_database
from bson.regex import Regex
from typing import Type
from loguru import logger

from cskg.entity import *
from cskg.relationship import *
from cskg.interpreter.interpreter import CodeInterpreter
from cskg.composer.composer import GraphComposer


RELS_EXTERNAL_ENTITIES_MAPPING: list[tuple[Type[Relationship], Type[Entity]]] = [
    (CallsRel, ExternalFunctionEntity),
    (InheritsRel, ExternalClassEntity),
    (ReturnsRel, ExternalClassEntity),
    (YieldsRel, ExternalClassEntity),
    (InstantiatesRel, ExternalClassEntity),
    (TakesRel, ExternalClassEntity),
]


class Driver:
    def __init__(self, folder_path: str, neo4j_url: str, mongo_url: str):
        self.folder_path = folder_path
        self.neo4j_url = neo4j_url
        self.mongo_url = mongo_url
        self.interpreter = None
        self.graph_composer = None
        self.__init_database()

    def __init_database(self):
        # Load neomodel configurations
        neomodel.config.DATABASE_URL = self.neo4j_url
        neomodel.config.AUTO_INSTALL_LABELS = True
        self.neo_db = neomodel.db
        self.neo_db.set_connection(self.neo4j_url)

        # Instantiate mongo db client
        mongo_client = MongoClient(self.mongo_url)
        mongo_db = mongo_client.code_interpreter
        self.mongo_client = mongo_client
        self.mongo_db = mongo_db

        # Clean up
        _mongo_drop_all(self.mongo_db)
        _neo_drop_all(self.neo_db)

    def run(self):
        # Instantiate
        self.interpreter = CodeInterpreter(self.folder_path)
        self.graph_composer = GraphComposer()

        # Interpretate codebase
        self.__interpret_code()
        self.__populate_external_entities()
        logger.info("Interpretation done")

        # Compose graph
        self.__compose_graph()
        logger.info("Composition done")

        logger.info("Done")

    def __interpret_code(self):
        generator = self.interpreter.interpret()

        with self.mongo_client.start_session() as session:
            while True:
                try:
                    obj = next(generator)
                    self.mongo_db[obj.type].insert_one(obj, session=session)
                    logger.info(obj)
                except StopIteration:
                    break
                except DuplicateKeyError as e:
                    logger.error(e)
                except Exception as e:
                    raise e

    def __compose_graph(self):
        modules = self.mongo_db[ModuleEntity.type].find()
        classes = self.mongo_db[ClassEntity.type].find()
        functions = self.mongo_db[FunctionEntity.type].find()
        methods = self.mongo_db[MethodEntity.type].find()
        variables = self.mongo_db[VariableEntity.type].find()
        calls_rels = self.mongo_db[CallsRel.type].find()
        inherits_rels = self.mongo_db[InheritsRel.type].find()
        contains_rels = self.mongo_db[ContainsRel.type].find()
        takes_rels = self.mongo_db[TakesRel.type].find()
        returns_rels = self.mongo_db[ReturnsRel.type].find()
        yields_rels = self.mongo_db[YieldsRel.type].find()
        instantiates_rels = self.mongo_db[InstantiatesRel.type].find()

        self.graph_composer.add_entities(modules)
        self.graph_composer.add_entities(classes)
        self.graph_composer.add_entities(functions)
        self.graph_composer.add_entities(methods)
        self.graph_composer.add_entities(variables)
        self.graph_composer.add_relationships(calls_rels)
        self.graph_composer.add_relationships(inherits_rels)
        self.graph_composer.add_relationships(contains_rels)
        self.graph_composer.add_relationships(takes_rels)
        self.graph_composer.add_relationships(returns_rels)
        self.graph_composer.add_relationships(yields_rels)
        self.graph_composer.add_relationships(instantiates_rels)

        self.graph_composer.compose()

    def __populate_external_entities(self):
        with self.mongo_client.start_session() as session:
            for rel, ent in RELS_EXTERNAL_ENTITIES_MAPPING:
                rels_collection = self.mongo_db[rel.type]
                ents_collection = self.mongo_db[ent.type]

                module_prefix = self.interpreter.get_module_prefix()
                regex_expr = Regex(f"^(?!{module_prefix}\.)")

                pipeline = [
                    {
                        "$match": {
                            "to_type": ent.type,
                            "to_qualified_name": regex_expr,
                        }
                    },
                    {
                        "$group": {
                            "_id": "$to_qualified_name",
                            "qualified_name": {"$first": "$to_qualified_name"},
                        }
                    },
                    {
                        "$project": ent(
                            _id=False,
                            name="$qualified_name",
                            qualified_name="$qualified_name",
                            file_path="<external>",
                        )
                    },
                ]

                try:
                    external_ents = rels_collection.aggregate(pipeline, session=session)
                    ents_collection.insert_many(external_ents, session=session)
                except InvalidOperation as e:
                    logger.error(e)


def _mongo_drop_all(mongo_db):
    for collection_name in mongo_db.list_collection_names():
        mongo_db.drop_collection(collection_name)


def _neo_drop_all(neo_db):
    clear_neo4j_database(neo_db, clear_constraints=True, clear_indexes=True)
