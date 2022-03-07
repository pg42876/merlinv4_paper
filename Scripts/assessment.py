import os
from typing import List

import pandas as pd
from cobra import Model

import numpy as np
from pandas import DataFrame
from sklearn.metrics import confusion_matrix

import seaborn as sns
import matplotlib.pyplot as plt

from matplotlib.patches import Circle, RegularPolygon
from matplotlib.path import Path
from matplotlib.projections.polar import PolarAxes
from matplotlib.projections import register_projection
from matplotlib.spines import Spine
from matplotlib.transforms import Affine2D

from Scripts.xrefs_converters import ReactionsConverter


class ModelAssessor:

    def __init__(self, reference_model: Model):
        self.y_true = None
        self.reference_model_reactions = None
        self.reference_model = reference_model

    @staticmethod
    def get_reactions_to_convert(model):

        all_reactions = model.model.reactions
        reactions_to_convert = []

        transport_reactions = {}

        for group in model.model.groups:
            reactions_list = []
            if "transport" in str(group.name).lower() or "drain" in str(group.name).lower():
                for member in group.members:
                    reactions_list.append(member.id)
                transport_reactions[str(group.name)] = reactions_list

        for reaction in all_reactions:
            reaction_id = reaction.id

            add = True

            # exclude exchange reactions from the comparison
            if len(model.model.exchanges) > 0 and add:
                if reaction in model.model.exchanges:
                    add = False

            if "drain" in str(reaction.name).lower() and add:
                add = False

            if "exchange" in str(reaction.name).lower() and add:
                add = False

            if str(reaction_id).upper().startswith("EX_") and add:
                add = False

            # exclude demand reactions from the comparison
            if len(model.model.demands) > 0 and add:
                if reaction in model.model.demands:
                    add = False

            # exclude transport reactions from the comparison
            if len(model.model.sinks) > 0 and add:
                if reaction in model.model.sinks:
                    add = False

            # exclude transport reactions from the comparison
            if "transport" in str(reaction.name).lower() and add:
                add = False

            if str(reaction_id).upper().startswith("TRANS-RXN") and add:
                add = False

            if "TRANS-RXN" in str(reaction.name).upper() and add:
                add = False

            if len(transport_reactions) > 0 and add:
                for group in transport_reactions.values():
                    if reaction_id in group:
                        add = False
                        break

            if add:
                reactions_to_convert.append(reaction_id)

        return reactions_to_convert

    @staticmethod
    def convert_reactions(models):
        reaction_sets = {}

        for model_name in models.keys():

            reaction_set = []
            model = models[model_name]

            reactions_to_convert = ModelAssessor.get_reactions_to_convert(model)
            #reactions_to_convert = [reaction.id for reaction in model.model.reactions]

            ModelSEED_reactions_converter = ReactionsConverter("xrefs_files/ModelSEED-reactions.csv")
            model.reaction_converter = ModelSEED_reactions_converter
            ModelSEED_report = model.get_reactions_other_version(database="modelseed",
                                                                 reactions=reactions_to_convert,
                                                                 preprocess_ids=True)
            ModelSEED_convertable_reactions = ModelSEED_report.convertable

            print("Tool: " + str(model.reconstruction_tool))
            print("Total number of reactions: " + str(len(model.model.reactions)))

            print("Reactions converted with ModelSEED: " + str(len(ModelSEED_convertable_reactions.keys())))
            print("Reactions not converted with ModelSEED: " + str(len(ModelSEED_report.non_convertable)))

            for convertable_reaction in ModelSEED_convertable_reactions:
                converted_reactions = ModelSEED_convertable_reactions[convertable_reaction]

                if len(converted_reactions) > 1:
                    dic = {}
                    for converted_reaction in converted_reactions:
                        dic[converted_reaction] = 0
                        for model in reaction_sets.keys():
                            if converted_reaction in reaction_sets[model]:
                                dic[converted_reaction] = int(dic[converted_reaction]) + 1

                    dic = dict(sorted(dic.items(), key=lambda item: item[1]))
                    reaction_set.append((str(list(dic.keys())[-1])).upper())
                else:
                    for converted_reaction in converted_reactions:
                        if converted_reaction not in reaction_set:
                            reaction_set.append(str(converted_reaction).upper())

            # ModelSEED_non_convertable_reactions = ModelSEED_report.non_convertable
            # MetaNetX_reactions_converter = ReactionsConverter("xrefs_files/MetaNetX-reactions.csv")
            # model.reaction_converter = MetaNetX_reactions_converter
            # MetaNetX_report = model.get_reactions_other_version(database="metanetx",
            #                                                     reactions=ModelSEED_non_convertable_reactions,
            #                                                     preprocess_ids=False)
            # MetaNetX_convertable_reactions = MetaNetX_report.convertable
            #
            # print("Reactions converted with MetaNetX: " + str(len(MetaNetX_convertable_reactions.keys())))
            # print("Reactions not converted with MetaNetX: " + str(len(MetaNetX_report.non_convertable)))
            # print(MetaNetX_report.non_convertable)
            # print()
            #
            # for convertable_reaction in MetaNetX_convertable_reactions:
            #     converted_reactions = MetaNetX_convertable_reactions[convertable_reaction]
            #
            #     if len(converted_reactions) > 1:
            #         dic = {}
            #         for converted_reaction in converted_reactions:
            #             dic[converted_reaction] = 0
            #             for model in reaction_sets.keys():
            #                 if converted_reaction in reaction_sets[model]:
            #                     dic[converted_reaction] = int(dic[converted_reaction]) + 1
            #
            #         dic = dict(sorted(dic.items(), key=lambda item: item[1]))
            #         reaction_set.append((str(list(dic.keys())[-1])).upper())
            #     else:
            #         for converted_reaction in converted_reactions:
            #             if converted_reaction not in reaction_set:
            #                 reaction_set.append(str(converted_reaction).upper())
            #
            reaction_sets[model_name] = set(reaction_set)
        return reaction_sets


class ModelAssessor2:

    def __init__(self, reference_model: Model):
        self.y_true = None
        self.bigg_reactions = pd.read_csv("bigg_reaction_database/bigg_models_reactions.txt", sep="\t")
        mask = self.bigg_reactions["bigg_id"].str.contains("DM_") | \
               self.bigg_reactions["bigg_id"].str.contains("EX_") | \
               self.bigg_reactions["bigg_id"].str.contains("BIOMASS_")

        self.bigg_reactions = list(self.bigg_reactions[~mask].loc[:, "bigg_id"].values)

        self.reference_model_reactions = [reaction.id for reaction in reference_model.reactions if
                                          all([forbidden not in reaction.id for forbidden in
                                               ["DM_", "EX_", "BIOMASS_"]])]

        self.get_y_true()

    def get_y_true(self):
        self.y_true = np.empty(len(self.bigg_reactions))

        for i, reaction in enumerate(self.bigg_reactions):
            if reaction in self.reference_model_reactions:
                self.y_true[i] = 1
            else:
                self.y_true[i] = 0

        return self.y_true

    def get_y_predicted(self, model_reactions: List[str]):
        y_predicted = np.empty(len(self.bigg_reactions))

        for i, reaction in enumerate(self.bigg_reactions):
            if reaction in model_reactions:
                y_predicted[i] = 1
            else:
                y_predicted[i] = 0

        return y_predicted

    def compare_model(self, model: Model, metrics: List[callable]):
        results = {}

        model_reactions = [reaction.id for reaction in model.reactions if
                           all([forbidden not in reaction.id for forbidden in ["DM_", "EX_", "BIOMASS_"]])]

        for metric in metrics:
            y_predicted = self.get_y_predicted(model_reactions)
            metric_result = metric(self.y_true, y_predicted)
            results[metric.__name__] = metric_result

        return results

    def plot_confusion_matrix(self, model: Model, output_file_path: str):

        model_reactions = [reaction.id for reaction in model.reactions if
                           all([forbidden not in reaction.id for forbidden in ["DM_", "EX_", "BIOMASS_"]])]

        y_predicted = self.get_y_predicted(model_reactions)
        cm = confusion_matrix(self.y_true, y_predicted)
        self.generate_confusion_matrix(cm, output_file_path)

    @staticmethod
    def generate_confusion_matrix(cm, output_path):
        index = ['Negative', 'Positive']
        columns = ['Negative', 'Positive']
        cm_df = pd.DataFrame(cm, columns, index)
        plt.figure(figsize=(10, 6))
        sns.heatmap(cm_df, annot=True, fmt=".8g")
        plt.savefig(output_path)


class ResultsReport:

    def __init__(self, reference_model: Model, models_to_be_assessed: List[Model]):
        self.model_assessor = ModelAssessor(reference_model)
        self.models_to_be_assessed = models_to_be_assessed

    def radar_factory(self, num_vars, frame='circle'):
        """Create a radar chart with `num_vars` axes.

        This function creates a RadarAxes projection and registers it.

        Parameters
        ----------
        num_vars : int
            Number of variables for radar chart.
        frame : {'circle' | 'polygon'}
            Shape of frame surrounding axes.

        """
        # calculate evenly-spaced axis angles
        theta = np.linspace(0, 2 * np.pi, num_vars, endpoint=False)

        class RadarAxes(PolarAxes):

            name = 'radar'

            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                # rotate plot such that the first axis is at the top
                self.set_theta_zero_location('N')

            def fill(self, *args, closed=True, **kwargs):
                """Override fill so that line is closed by default"""
                return super().fill(closed=closed, *args, **kwargs)

            def plot(self, *args, **kwargs):
                """Override plot so that line is closed by default"""
                lines = super().plot(*args, **kwargs)
                for line in lines:
                    self._close_line(line)

                return lines

            def _close_line(self, line):
                x, y = line.get_data()
                # FIXME: markers at x[0], y[0] get doubled-up
                if x[0] != x[-1]:
                    x = np.concatenate((x, [x[0]]))
                    y = np.concatenate((y, [y[0]]))
                    line.set_data(x, y)

            def set_varlabels(self, labels):
                self.set_thetagrids(np.degrees(theta), labels)

            def _gen_axes_patch(self):
                # The Axes patch must be centered at (0.5, 0.5) and of radius 0.5
                # in axes coordinates.
                if frame == 'circle':
                    return Circle((0.5, 0.5), 0.5)
                elif frame == 'polygon':
                    return RegularPolygon((0.5, 0.5), num_vars,
                                          radius=.5, edgecolor="k")
                else:
                    raise ValueError("unknown value for 'frame': %s" % frame)

            def draw(self, renderer):
                """ Draw. If frame is polygon, make gridlines polygon-shaped """
                if frame == 'polygon':
                    gridlines = self.yaxis.get_gridlines()
                    for gl in gridlines:
                        gl.get_path()._interpolation_steps = num_vars
                super().draw(renderer)

            def _gen_axes_spines(self):
                if frame == 'circle':
                    return super()._gen_axes_spines()
                elif frame == 'polygon':
                    # spine_type must be 'left'/'right'/'top'/'bottom'/'circle'.
                    spine = Spine(axes=self,
                                  spine_type='circle',
                                  path=Path.unit_regular_polygon(num_vars))
                    # unit_regular_polygon gives a polygon of radius 1 centered at
                    # (0, 0) but we want a polygon of radius 0.5 centered at (0.5,
                    # 0.5) in axes coordinates.
                    spine.set_transform(Affine2D().scale(.5).translate(.5, .5)
                                        + self.transAxes)

                    return {'polar': spine}
                else:
                    raise ValueError("unknown value for 'frame': %s" % frame)

        register_projection(RadarAxes)
        return theta

    def generate_confusion_matrices(self, output_folder_path: str):

        os.makedirs(output_folder_path, exist_ok=True)

        for i, model in enumerate(self.models_to_be_assessed):
            self.model_assessor.plot_confusion_matrix(model, os.path.join(output_folder_path,
                                                                          model.id))

    def generate_report_csv(self, metrics: List[callable], output_file_path: str):
        results = DataFrame()

        for i, model in enumerate(self.models_to_be_assessed):
            metrics_results = self.model_assessor.compare_model(model, metrics)
            results.at[i, "model"] = model.id
            for metric in metrics_results:
                results.at[i, metric] = metrics_results[metric]

        results.to_csv(output_file_path, index=False)

    def generate_radar_graph(self, metrics, metrics_names, output_file):
        results = []
        for i, model in enumerate(self.models_to_be_assessed):
            metrics_results = self.model_assessor.compare_model(model, metrics)
            metrics_results_list = []
            for metric in metrics_results:
                metrics_results_list.append(metrics_results[metric])

            results.append(metrics_results_list)

        data = [metrics_names,
                ('Approaches performance', results)]

        N = len(data[0])
        theta = self.radar_factory(N, frame='circle')

        spoke_labels = data.pop(0)
        title, case_data = data[0]

        fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(projection='radar'))
        fig.subplots_adjust(top=0.85, bottom=0.05)

        ax.set_rgrids([0.2, 0.4, 0.6, 0.8])
        ax.set_title(title, position=(0.5, 1.1), ha='center')
        lax = []
        for i, d in enumerate(case_data):
            line = ax.plot(theta, d)
            ax.fill(theta, d, alpha=0.25)
            lax.append(line[0])

        index = [model.id for model in self.models_to_be_assessed]
        ax.legend(handles=lax, labels=index, loc='lower right')
        ax.set_varlabels(spoke_labels)

        plt.savefig(output_file)
