from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


class Container(db.Model):
    __tablename__ = 'containers'

    id = db.Column(db.Integer, primary_key=True)
    container_no = db.Column(db.String(30), unique=True, nullable=False)
    container_type = db.Column(db.String(10), nullable=False)
    is_full = db.Column(db.Boolean, default=False)
    is_dangerous = db.Column(db.Boolean, default=False)
    is_refrigerated = db.Column(db.Boolean, default=False)
    yard = db.Column(db.String(20))
    area = db.Column(db.String(20))
    column = db.Column(db.Integer)
    layer = db.Column(db.Integer)
    status = db.Column(db.String(20), default='\u5728\u8239\u4e2d')

    def to_dict(self):
        return {
            "id": self.id,
            "container_no": self.container_no,
            "container_type": self.container_type,
            "is_full": self.is_full,
            "is_dangerous": self.is_dangerous,
            "is_refrigerated": self.is_refrigerated,
            "yard": self.yard,
            "area": self.area,
            "column": self.column,
            "layer": self.layer,
            "status": self.status
        }
