/**
This file is part of tumorcode project.
(http://www.uni-saarland.de/fak7/rieger/homepage/research/tumor/tumor.html)

Copyright (C) 2016  Michael Welter and Thierry Fredrich

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
*/
#include "oxygen_model.h"
#include "shared-objects.h"
#include "continuum-flow.h"
#include <boost/property_tree/info_parser.hpp>
namespace O2Model
{

  static const string tissue_name[] = {
  "tumor",
  "necro",
  "normal"
  };
  
PrezO2Params::PrezO2Params()
{
  o2_rel_tumor_source_density = 0.2;
  o2_level_normal = 0.8;
  for (int i=0; i<3; ++i)
  {
    o2_range[i] = 100.;
    o2_cons_coeff[i] = 1./my::sqr(o2_range[i]);
  }
  test_obstacle = 0;
  use_o2_source_decay = false;
}

#define PT_ASSIGN(name) boost::property_tree::get(name, #name, pt)
#define AS_PTREE(name) pt.put(#name, name);
void PrezO2Params::assign(const ptree &pt)
{
  #define DOPT(name) boost::property_tree::get(name, #name, pt)
  for (int i=0; i<3; ++i) 
  {
    std::string name_coeff = "o2_cons_coeff_"+tissue_name[i];
    std::string name_range = "o2_range_"+tissue_name[i];
    boost::optional<float> c = pt.get_optional<float>(name_coeff);
    boost::optional<float> r = pt.get_optional<float>(name_range);
    
    if (r)
    {
      o2_range[i] = *r;
      o2_cons_coeff[i] = 1./my::sqr(*r);
    }
    else if (c)
    {
      o2_range[i] = 1.0/std::sqrt(*c);
      o2_cons_coeff[i] = *c;
    }
    else
      throw std::invalid_argument("either o2_cons_coeff_<tissue type> or o2_range_<tissue type> must be provided");
  }
  DOPT(o2_level_normal);
  PT_ASSIGN(o2_rel_tumor_source_density);
  PT_ASSIGN(test_obstacle);
  PT_ASSIGN(use_o2_source_decay);
  #undef DOPT
}


void PrezO2Params::update_ptree(ptree &dst, const ptree &src)
{
  boost::property_tree::update(dst, src);
  for (int i=0; i<3; ++i)
  {
    double range = 0., cons_coeff = 0.;
    cout << "set params are in update ptree are: ";
    boost::property_tree::write_info(cout, src);
    cout << endl;
    O2Model::assignRangeParam(range, cons_coeff, "_"+tissue_name[i], src);
    
    dst.put("o2_range_"+tissue_name[i], range);
    dst.put("o2_cons_coeff_"+tissue_name[i], cons_coeff);
  }
}


ptree PrezO2Params::as_ptree() const
{
  ptree pt;
  #define DOPT(name) pt.put(#name, name)
  #define DOPT2(name, i) pt.put(#name"_"+tissue_name[i], name[i])

  DOPT(o2_level_normal);
  for (int i=0; i<3; ++i)
  {
    DOPT2(o2_range, i);
    DOPT2(o2_cons_coeff, i);
  }
  
  AS_PTREE(o2_rel_tumor_source_density);
  AS_PTREE(test_obstacle);
  pt.put("o2_source_decay_time", 8);
  AS_PTREE(use_o2_source_decay);
  #undef DOPT
  #undef DOPT2
  return pt;
}
  
void AddSourceDistribution(const BBox3 &bbox, const LatticeDataQuad3d &field_ld, int dim, Array3d<float> l_coeff, Array3d<float> rhs, const VesselList3d::LatticeData &vessld, const DynArray<const Vessel*> &vessels, const ptree &params)
{
  const double capillary_wall_permeability = params.get<double>("capillary_wall_permeability");
  const double coeffBloodOxy   = 1.0f;

  const double maturation_at_r5 = GetInitialThickness(5.0f);
  //const double maturation_at_r20= GetInitialThickness(20.0f);
  const double hematocrit_init = params.get<double>("hematocrit_init");
/* In 2d, the samples are projected on the xy plane.
   It is assumed that a 2d slice is 200 micron in height. Hence the scaling factor. */
  const double dim_coeff = dim==2 ? (field_ld.Scale()/params.get<double>("fake_height_2d",200.)) : 1.;
  
  CylinderNetworkSampler sampler; sampler.Init(field_ld.Scale(), params);
  for (int i=0; i<vessels.size(); ++i)
  {
    const Vessel* v = vessels[i];
    if( !v->IsCirculated() ) continue;
    
    float o2level = coeffBloodOxy * v->hematocrit / hematocrit_init;
    myAssert(v->hematocrit > 0.);
    //float perm = capillary_wall_permeability * maturation_at_r5 / std::max<float>(maturation_at_r20, v->maturation);  // maturation has the value of vessel wall thickness, have to limit it so the coefficient does not become infinite
    //float perm = capillary_wall_permeability * 1./std::max<float>(1., v->maturation / maturation_at_r5);
    float perm = capillary_wall_permeability;
    myAssert(v->maturation > 0.);
    float loc_l_coef = -perm*dim_coeff;
    float loc_rhs = -perm*o2level*dim_coeff;

    myAssert(std::isfinite(loc_l_coef) && std::isfinite(loc_rhs));

    sampler.Set(vessld.LatticeToWorld(v->LPosA()), vessld.LatticeToWorld(v->LPosB()), v->r);
    int cnt = sampler.GenerateSurfaceSamples();
    for (int j=0; j<cnt; ++j)
    {
      const CylinderNetworkSampler::Sample &s = sampler.GetSample(j);

      AddSmoothDelta(l_coeff, bbox, field_ld, dim, s.wpos, sampler.weight_per_volume*loc_l_coef);
      AddSmoothDelta(rhs, bbox, field_ld, dim, s.wpos, sampler.weight_per_volume*loc_rhs);
    }
  }
}

void AddSourceDistribution(Array3d<float> clinear_field, Array3d<float> rhs_field, int dim, const LatticeDataQuad3d &field_ld,
                                 const VesselList3d &vl,
                                 const boost::property_tree::ptree &params)
{
  DynArray<const Vessel*> vessels(vl.GetECount());
  for (int i=0; i<vl.GetECount(); ++i)
    vessels[i] = vl.GetEdge(i);
  AddSourceDistribution(field_ld.Box(), field_ld, dim, clinear_field, rhs_field, vl.Ld(), vessels, params);
}


void assignRangeParam(double &range, double &cons_coeff, const string &parameter_postfix, const ptree &pt)
{
  boost::optional<double> opt_range = pt.get_optional<double>("o2_range"+parameter_postfix);
  if (opt_range)
  {
    range = *opt_range;
    cons_coeff = 1./my::sqr(range);
  }
  else
  {
    cons_coeff = pt.get<double>("o2_cons_coeff"+parameter_postfix);
    range = 1./std::sqrt(cons_coeff);
  }
}


void assignWallPermeabilityCoefficient(double &capillary_wall_permeability, double &o2_level_normal, double consumption_coeff, double reference_intercapillary_distance, double capillary_radius, const ptree &pt)
{
  boost::optional<double> opt_level = pt.get_optional<double>("o2_level_normal");
  if (opt_level)
  {
    o2_level_normal = *opt_level;
    capillary_wall_permeability = CalcHomogeneousCoeffOxy(consumption_coeff, o2_level_normal, capillary_radius, reference_intercapillary_distance);
  }
  else
  {
    capillary_wall_permeability = pt.get<double>("capillary_wall_permeability");
    o2_level_normal = CalcHomogeneousMaxOxy(consumption_coeff, capillary_wall_permeability, capillary_radius, reference_intercapillary_distance);
  }
}




//-----------------------------------
//-----------------------------------

double CalcHomogeneousMaxOxy(double c, double q, double vess_rad, double vess_spacing)
{
  const int dim = 3;
  double mvd = vess_spacing * dim*std::pow(1./vess_spacing, dim);
  double surf_area_per_volume = my::mconst::pi2() * vess_rad * mvd;
  q *= surf_area_per_volume;
  return q / (c + q);
}

double CalcHomogeneousCoeffOxy(double c, double hmax, double vess_rad, double vess_spacing)
{
  const int dim = 3;
  double q = hmax * c / (1. - hmax);
  double mvd = vess_spacing * dim*std::pow(1./vess_spacing, dim);
  double surf_area_per_volume = my::mconst::pi2() * vess_rad * mvd;
  return q / surf_area_per_volume;
}


}
