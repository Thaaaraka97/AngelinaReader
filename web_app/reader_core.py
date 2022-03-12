#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
Description of interfaces between UI and algorithmic modules
"""
from datetime import datetime
from enum import Enum
import json
import hashlib
import os
from pathlib import Path
import sqlite3
import time
import timeit
import uuid
import werkzeug.datastructures

from .config import Config
import model.infer_retinanet as infer_retinanet

MODEL_PATH = Config.MODEL_PATH or Path(__file__).parent.parent
MODEL_WEIGHTS = 'model.t7'

recognizer = None

class TaskState(Enum):
    CREATED = 0
    RAW_FILE_LOADED = 1
    PROCESSING_STARTED = 2
    PROCESSING_DONE = 3
    ERROR = 4
    START_TEXT_TIME = 5  # GVNC

VALID_EXTENTIONS = tuple('jpg jpe jpeg png'.split())

class User:
    """
    System user and its attributes
    Create class instances via AngelinaSolver.find_user or AngelinaSolver.register_user
    """
    def __init__(self, id, user_dict, solver):
        """
        Below is a list of attributes for demo
        All attributes - read only, change through calls to the appropriate methods
        """
        self.id = id  # system-unique user id. Assigned upon registration.
        self.solver = solver
        self.name = user_dict.get("name", "")
        self.email = user_dict.get("email", "")

        # Data with which the user was found via find_user or created via register_user.
        # A user can have multiple login methods, so
        self.network_name = user_dict.get("network_name")       
        self.network_id = user_dict.get("network_id")
        self.password_hash = user_dict.get("password_hash")
        self.params = user_dict.get("params")
        if self.params:
            self.params_dict = json.loads(self.params)
        else:
            self.params_dict = dict()

        # fields for Flask:
        self.is_authenticated = id is not None
        self.is_active = True
        self.is_anonymous = id is None

    def get_id(self):
        return self.id

    def hash_password(self, password):
        return hashlib.sha512(password.encode('utf-8')).hexdigest()
        
    def check_password(self, password):
        """
        Checks the password. Call about login by email.
        """
        password_hash = self.hash_password(password)
        if self.password_hash == password_hash:
            return True
        if self.params:
            params = json.loads(self.params)
            if params.get('tmp_password') == password_hash:
                return True
        return False    

def exec_sqlite(con, query, params, timeout=10):
    """
    Attempts to execute a command over sqlite, on error repeats for timeout seconds.
    :param con: connection
    :param query: sql text
    :param params: tuple or dict of params
    :param timeout: seconds
    :return: result of query
    """
    t0 = timeit.default_timer()
    i = 0
    while True:
        i += 1
        try:
            res = con.cursor().execute(query, params).fetchall()
            con.commit()
            return res
        except sqlite3.OperationalError as e:
            t = timeit.default_timer()
            if t > t0 + timeout:
                raise Exception("{} {} times {} to {} for {}".format(str(e), i, t, t0, query))
            time.sleep(0.1)

class AngelinaSolver:
    """
    Provides an interface with the computing system: users, tasks and processing results
    """
    def __init__(self, data_root_path):
        self.data_root = Path(data_root_path)
        self.tasks_dir = Path('tasks')
        self.raw_images_dir = Path('raw')
        self.results_dir = Path('results')
        os.makedirs(self.data_root, exist_ok=True)
        self.users_db_file_name = self.data_root / "all_users.db"

    def get_recognizer(self):
        global recognizer
        if recognizer is None:
            print("infer_retinanet.BrailleInference()")
            t = timeit.default_timer()
            recognizer = infer_retinanet.BrailleInference(verbose=2,
                params_fn=os.path.join(MODEL_PATH, 'weights', 'param.txt'),
                model_weights_fn=os.path.join(MODEL_PATH, 'weights', MODEL_WEIGHTS),
                create_script=None)
            print(timeit.default_timer() - t)
        return recognizer

    # ##########################################
    # ## work with users
    # ##########################################

    def find_user(self, network_name=None, network_id=None, email=None, id=None):
        """
        Returns a User object by registration data: id or a pair of network_name + network_id or registration by email (for this, specify network_name = None or network_name = "")
        If the user is not found, returns None
        """
        con = self._users_sql_conn()
        con.row_factory = sqlite3.Row
        if id:
            assert not network_name and not network_id and not email, ("incorrect call to find_user 1", network_name, network_id, email)
            query = ("select * from users where id = ?", (id,))
        elif network_name or network_id:
            assert network_name and network_id, ("incorrect call to find_user 2", network_name, network_id, email)
            query = ("select * from users where network_name = ? and network_id = ?", (network_name,network_id,))
        else:
            assert email and not network_name and not network_id, ("incorrect call to find_user 3", network_name, network_id, email)
            query = ("select * from users where email = ? and (network_name is NULL or network_name='') and (network_id is NULL or network_id='')", (email,))
        res = exec_sqlite(con, query[0], query[1])
        if len(res):
            user_dict = dict(res[0])  # sqlite row -> dict
            assert len(res) <= 1, ("more then 1 user found", user_dict)
            user = User(id=user_dict["id"], user_dict=user_dict, solver=self)
            return user
        return None  # Nothing found

    def _users_sql_conn(self):
        timeout = 0.1
        new_db = not os.path.isfile(self.users_db_file_name)
        con = sqlite3.connect(str(self.users_db_file_name), timeout=timeout)
        if new_db:
            con.cursor().execute(
                "CREATE TABLE users(id text PRIMARY KEY, name text, email text, network_name text, network_id text, password_hash text, reg_date text, params text)")
            self._convert_users_from_json(con)
            con.commit()
        return con

    def _convert_users_from_json(self, con):
        import json
        json_file = os.path.splitext(self.users_db_file_name)[0] + '.json'
        if os.path.isfile(json_file):
            with open(json_file, encoding='utf-8') as f:
                all_users = json.load(f)
            for id, user_dict in all_users.items():
                con.cursor().execute("INSERT INTO users(id, name, email) VALUES(?, ?, ?)",
                                     (id, user_dict["name"], user_dict["email"]))

    def _user_tasks_sql_conn(self, user_id):
        timeout = 0.1
        db_dir = self.data_root / self.tasks_dir
        if not user_id:
            user_id = "unregistered"
        db_path = db_dir / (user_id + ".db")
        new_db = not os.path.isfile(db_path)
        if new_db:
            os.makedirs(db_dir, exist_ok=True)
        con = sqlite3.connect(str(db_path), timeout=timeout)
        if new_db:
            con.cursor().execute(
                "CREATE TABLE tasks(doc_id text PRIMARY KEY, create_date text, name text, user_id text, params text,"
                " raw_paths text, state int, results text, thumbnail text, is_public int, thumbnail_desc text, is_deleted int)")
            con.commit()
        return con


    # actual recognition
    def process(self, user_id, file_storage, param_dict):
        """
        user: User ID or None for anonymous access
        file_storage: werkzeug.datastructures.FileStorage: uploaded image, pdf or zip or a list of full image paths
        param_dict: includes
            lang: user selected language ('SIN')
            find_orientation: bool, find orientation
            process_2_sides: bool, recognize both sides
            has_public_confirm: bool, the user has confirmed the public availability of the results
        timeout: time to wait for the result. If None or < 0 - wait until completed. 0 queue and don't wait.
        
        Queues a task for recognition and waits for its completion within the timeout.
        After successful loading, we return the id of the materials in the recognition system or False if during processing
        request encountered an error. Next, by this id, we go to the page for viewing the results of this recognition
        """
        doc_id = uuid.uuid4().hex
        if type(file_storage) == werkzeug.datastructures.ImmutableMultiDict:
            file_storage = file_storage['file']
        assert type(file_storage) == werkzeug.datastructures.FileStorage, type(file_storage)
        task_name = file_storage.filename
        if not user_id:
            user_id = ""
        task = {
            "doc_id": doc_id,
            "create_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "name": task_name,
            "user_id": user_id,
            "params": json.dumps(param_dict),
            "raw_paths": None,
            "state": TaskState.CREATED.value,
            "results": None,
            "thumbnail": "",
            "is_public": int(param_dict["has_public_confirm"]),
            "thumbnail_desc": "",
            "is_deleted": 0
        }
        con = self._user_tasks_sql_conn(user_id)
        exec_sqlite(con, "insert into tasks(doc_id, create_date, name, user_id, params, raw_paths, state, results,"
                         " thumbnail, is_public, thumbnail_desc, is_deleted)"
                         " values(:doc_id, :create_date, :name, :user_id, :params, :raw_paths, :state, :results,"
                         " :thumbnail, :is_public, :thumbnail_desc, :is_deleted)", task)

        file_ext = Path(task_name).suffix.lower()
        assert file_ext[1:] in VALID_EXTENTIONS, "incorrect file type: " + str(task_name)

        os.makedirs(self.data_root / self.raw_images_dir, exist_ok=True)
        raw_image_fn = doc_id + file_ext
        raw_path = self.data_root / self.raw_images_dir / raw_image_fn
        file_storage.save(str(raw_path))

        task["raw_paths"] = raw_image_fn
        task["state"] = TaskState.RAW_FILE_LOADED.value
        exec_sqlite(con, "update tasks set raw_paths=:raw_paths, state=:state where doc_id=:doc_id", task)
        return user_id + "_" + doc_id

    def is_completed(self, task_id, timeout=0):
        """
        Checks if the task with the given id has completed
        """
        user_id, doc_id = task_id.split("_")
        task = { "doc_id": doc_id }
        con = self._user_tasks_sql_conn(user_id)
        result = exec_sqlite(con, "select params, raw_paths, state from tasks where doc_id=:doc_id", task)
        assert len(result) == 1, (user_id, doc_id, len(result))
        task = {
            **task,
            "params": result[0][0],
            "raw_paths": result[0][1],
            "state": result[0][2]
        }
        if task["state"] == TaskState.PROCESSING_DONE.value:
            return True

        # GVNC
        gvnc_mode = False
        if task["state"] == TaskState.RAW_FILE_LOADED.value and not timeout:
            task["state"] = TaskState.START_TEXT_TIME.value
            exec_sqlite(con, "update tasks set state=:state where doc_id=:doc_id", task)
            return False
        if task["state"] == TaskState.START_TEXT_TIME.value:
            task["state"] = TaskState.RAW_FILE_LOADED.value
            exec_sqlite(con, "update tasks set state=:state where doc_id=:doc_id", task)
            timeout = 2
            gvnc_mode = True

        if task["state"] != TaskState.RAW_FILE_LOADED.value or not timeout:
            return False

        ### calculations
        task["state"] = TaskState.PROCESSING_STARTED.value
        exec_sqlite(con, "update tasks set state=:state where doc_id=:doc_id", task)
        file_ext = Path(task["raw_paths"]).suffix.lower()
        raw_path = self.data_root / self.raw_images_dir / task["raw_paths"]
        param_dict = json.loads(task["params"])
        if file_ext[1:] == 'zip':
            results_list = self.get_recognizer().process_archive_and_save(raw_path, self.data_root / self.results_dir,
                                                                    lang=param_dict['lang'], extra_info=param_dict,
                                                                    draw_refined=self.get_recognizer().DRAW_NONE,
                                                                    remove_labeled_from_filename=False,
                                                                    find_orientation=param_dict['find_orientation'],
                                                                    align_results=True,
                                                                    process_2_sides=param_dict['process_2_sides'],
                                                                    repeat_on_aligned=False)

        else:
            results_list = self.get_recognizer().run_and_save(raw_path, self.data_root / self.results_dir, target_stem=None,
                                                        lang=param_dict['lang'], extra_info=param_dict,
                                                        draw_refined=self.get_recognizer().DRAW_NONE,
                                                        remove_labeled_from_filename=False,
                                                        find_orientation=param_dict['find_orientation'],
                                                        align_results=True,
                                                        process_2_sides=param_dict['process_2_sides'],
                                                        repeat_on_aligned=False)
        if results_list is None:
            task["state"] = TaskState.ERROR.value
            exec_sqlite(con, "update tasks set state=:state where doc_id=:doc_id", task)
            return False

        # full path -> relative to data path
        result_files = list()
        for marked_image_path, recognized_text_path, recognized_braille_path, _ in results_list:
            marked_image_path = str(Path(marked_image_path).relative_to(self.data_root / self.results_dir))
            recognized_text_path =  str(Path(recognized_text_path).relative_to(self.data_root / self.results_dir))
            recognized_braille_path = str(Path(recognized_braille_path).relative_to(self.data_root / self.results_dir))
            result_files.append((marked_image_path, recognized_text_path, recognized_braille_path))

        task["state"] = TaskState.PROCESSING_DONE.value
        task["results"] = json.dumps(result_files)
        task["thumbnail"] = "pic.jpg"  # TODO
        with (self.data_root / self.results_dir / result_files[0][1]).open(encoding="utf-8") as f:
            task["thumbnail_desc"] = ''.join(f.readlines()[:3])
        exec_sqlite(con, "update tasks set state=:state, results=:results, thumbnail=:thumbnail, thumbnail_desc=:thumbnail_desc where doc_id=:doc_id", task)
        if gvnc_mode:  # GVNC
            return False
        return True

    def get_results(self, task_id):
        """
        Returns recognition results for task_id.
        
        Returns a dictionary with fields:
            {"name": str,
             "create_date": datetime,
             "protocol": path to protocol.txt
            "item_data": list of results by number of pages in the task.
            Each list item is a tuple of full paths to files with image, text, braille
            }
        """

        user_id, doc_id = task_id.split("_")

        prev_slag = next_slag = result = None
        con = self._user_tasks_sql_conn(user_id)
        if user_id:
            results = exec_sqlite(con, "select doc_id, name, create_date, params, state, results, is_public"
                                       " from tasks"
                                       " where user_id=:user_id and is_deleted=0"
                                       " order by create_date desc",
                                       {"user_id": user_id})
            for r in results:
                if r[0] == doc_id:
                    result = r
                else:
                    if result is None:
                        next_slag = user_id + "_" + r[0]
                    else:
                        prev_slag = user_id + "_" + r[0]
                        break
        else:
            results = exec_sqlite(con, "select doc_id, name, create_date, params, state, results, is_public"
                                      " from tasks"
                                      " where doc_id=:doc_id and is_deleted=0",
                                      {"doc_id": doc_id})
            assert len(results) == 1, (user_id, doc_id)
            result = results[0]
        assert result is not None
        assert result[4] == TaskState.PROCESSING_DONE.value, (user_id, doc_id, result[4])
        item_data = list([
            tuple(
                str(
                    (Path("/static/data") if item_idx == 0 else self.data_root)  # GVNC needs to be moved to UI "/" + str(self.data_root / needs to be moved to UI
                    / self.results_dir / item
                )
                for item_idx, item in enumerate(id))
            for id in json.loads(result[5])
        ])
        res_dict = {
                "prev_slag":prev_slag,
                "next_slag":next_slag,
                "name":result[1],
                "create_date": datetime.strptime(result[2], "%Y-%m-%d %H:%M:%S"), #"20200104 200001",
                "item_data": item_data,
                "public": bool(result[6]),
                "protocol": json.loads(result[3])
                }
        return res_dict

    def get_tasks_list(self, user_id, count=None):
        """
        count - number of records
        Returns a list of task_id tasks for the given user, sorted from oldest to newest
        """
        """
        In the test case, it returns a list of 2 demo results taken 10 times.
        At the same time, at first they are all shown as not finished. As calculations are simulated, it is shown
        more realistic: the example is displayed as not ready 2 seconds after recognition is started
        Public - private - through one
        """
        if not user_id:
            return []
        con = self._user_tasks_sql_conn(user_id)
        results = exec_sqlite(con, "select doc_id, create_date, name, thumbnail, thumbnail_desc, is_public, state"
                                   " from tasks where user_id=:user_id and is_deleted=0"
                                   " order by create_date desc",
                    {"user_id": user_id})
        lst = [
                  {
                    "id": user_id + "_" + rec[0],
                    "date": datetime.strptime(rec[1], "%Y-%m-%d %H:%M:%S"),
                    "name": rec[2],
                    #"img_url":"/static/data/" + str(self.results_dir / rec[3]),
                    "img_url":"/static/images/pic.jpg",   # GVNC
                    "desc": rec[4],
                    "public": bool(rec[5]),
                    "sost": rec[6] == TaskState.PROCESSING_DONE.value
                   }
            for rec in results
        ]
        if count:
            lst = lst[:count]
        return lst

    def set_public_acceess(self, task_id, new_is_public):
        """
            The state of publicity is set in accordance with the passed is_public
            True - Public (The lock is open)
        """
        user_id, doc_id = task_id.split("_")
        con = self._user_tasks_sql_conn(user_id)
        exec_sqlite(con, "update tasks set is_public=:new_is_public where doc_id=:doc_id",
                    {"new_is_public": int(new_is_public), "doc_id": doc_id})
        return new_is_public


if __name__ == "__main__":
    core = AngelinaSolver()
    
    
