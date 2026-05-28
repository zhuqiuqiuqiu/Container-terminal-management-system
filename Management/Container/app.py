from pathlib import Path

from flask import Flask

from config import Config
from Container.models.container_model import Container, db
from routes.container_route import container_bp


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    app.register_blueprint(container_bp)

    with app.app_context():
        db.create_all()
        seed_data()

    return app


def seed_data():
    if Container.query.first():
        return

    test_data = [
        Container(
            container_no='A01',
            container_type='20GP',
            yard='\u4e0a\u6d77\u6e2f',
            status='\u5728\u8239\u4e2d'
        ),
        Container(
            container_no='A02',
            container_type='40HQ',
            yard='\u5b81\u6ce2\u6e2f',
            status='\u5806\u573a\u5b58\u50a8'
        ),
        Container(
            container_no='B01',
            container_type='40GP',
            yard='\u6df1\u5733\u6e2f',
            status='\u7b49\u5f85\u63d0\u7bb1'
        ),
    ]
    db.session.add_all(test_data)
    db.session.commit()


app = create_app()


if __name__ == '__main__':
    app.run(debug=True)
