from rest_framework import serializers
from .models import Project, Asset, Concept2D, MeetingSession, TranscriptSegment, GenerationJob

class SegmentSerializer(serializers.ModelSerializer):
    class Meta: model = TranscriptSegment; fields = ['start','end','speaker','text','confidence','chunk_index']
class MeetingSerializer(serializers.ModelSerializer):
    segments = SegmentSerializer(many=True, read_only=True)
    class Meta: model = MeetingSession; fields = ['status','transcript','analysis','chunk_count','provider','segments']
class ConceptSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='concept_id')
    url = serializers.CharField(source='public_url')
    absolute_path = serializers.CharField(source='relative_path')
    class Meta: model = Concept2D; fields = ['id','title','description','url','absolute_path','metadata']
class AssetSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source='original_name')
    url = serializers.CharField(source='public_url')
    absolute_path = serializers.CharField(source='relative_path')
    class Meta: model = Asset; fields = ['name','url','absolute_path','kind','metadata']
class ProjectSerializer(serializers.ModelSerializer):
    results_2d = ConceptSerializer(source='concepts', many=True, read_only=True)
    source_images = serializers.SerializerMethodField()
    meeting = MeetingSerializer(read_only=True)
    class Meta:
        model = Project
        fields = ['id','prompt','category','status','progress','step','results_2d','selected_2d_id','result_3d','analysis','pipeline','revision','meeting','source_images','design_state','generation_plan','validation_report','validation_grade','output_goal','quality_profile','generation_history','created_at','updated_at']
    def get_source_images(self,obj):
        return AssetSerializer(obj.assets.filter(kind='source_image'),many=True).data
class JobSerializer(serializers.ModelSerializer):
    class Meta: model = GenerationJob; fields = '__all__'
