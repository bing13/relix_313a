# see https://docs.djangoproject.com/en/3.0/topics/http/urls/
# p = re.compile('-?\d*^')
class PosNegInteger:
    regex = '-?\d*^'
    def to_python(self, value):
        # could return as int, but that will mess up all the matching we do
        #   on some of these values in the views.
        return str(value)

    def to_url(self, value):
        return str(value)
